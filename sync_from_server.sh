#!/bin/bash
# ==============================================================================
# GLPI Remote to Local Environment Synchronization Script
# Automatically pulls a database dump from the Development Server.
# ==============================================================================

set -euo pipefail

SERVER_IP="${SERVER_IP:-192.168.1.189}"
SERVER_USER="${SERVER_USER:-glpiusr}"
SSHPASS_BIN="${SSHPASS_BIN:-/opt/homebrew/bin/sshpass}"

REMOTE_DB_USER="${REMOTE_DB_USER:-glpiuser}"
REMOTE_DB_NAME="${REMOTE_DB_NAME:-glpidb}"
LOCAL_DB_CONTAINER="${LOCAL_DB_CONTAINER:-glpi_db}"
LOCAL_DB_USER="${LOCAL_DB_USER:-glpi}"
LOCAL_DB_NAME="${LOCAL_DB_NAME:-glpidb}"
DUMP_PATH="${DUMP_PATH:-glpi_remote_dump.sql}"

: "${SERVER_PASS:?Export SERVER_PASS before running this script}"
: "${REMOTE_DB_PASS:?Export REMOTE_DB_PASS before running this script}"
: "${LOCAL_DB_PASSWORD:?Export LOCAL_DB_PASSWORD before running this script}"

trap 'unset SERVER_PASS REMOTE_DB_PASS LOCAL_DB_PASSWORD' EXIT

if [ ! -x "$SSHPASS_BIN" ]; then
  echo "Error: sshpass executable not found at $SSHPASS_BIN."
  exit 1
fi

for identifier in "$REMOTE_DB_USER" "$REMOTE_DB_NAME" "$LOCAL_DB_CONTAINER" "$LOCAL_DB_USER" "$LOCAL_DB_NAME"; do
  if [[ ! "$identifier" =~ ^[A-Za-z0-9_.-]+$ ]]; then
    echo "Error: invalid database or container identifier."
    exit 1
  fi
done

echo "Checking connectivity to GLPI Server ($SERVER_IP)..."

if ! ping -c 1 -W 2 "$SERVER_IP" > /dev/null 2>&1; then
  echo "Error: unable to reach server at $SERVER_IP."
  echo "Check the network connection or VPN."
  exit 1
fi

echo "Server reachable. Fetching remote database dump..."

remote_dump_command=$(printf \
  'MYSQL_PWD=%q mysqldump -h 127.0.0.1 -u %q %q' \
  "$REMOTE_DB_PASS" "$REMOTE_DB_USER" "$REMOTE_DB_NAME")

SSHPASS="$SERVER_PASS" "$SSHPASS_BIN" -e \
  ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" \
  "$remote_dump_command" > "$DUMP_PATH" 2>/dev/null

if [ ! -s "$DUMP_PATH" ]; then
  echo "Warning: database dump failed or is empty."
  exit 1
fi

echo "Database dump downloaded to $DUMP_PATH."
echo "Restoring the dump into local Docker container $LOCAL_DB_CONTAINER..."

docker exec -e MYSQL_PWD="$LOCAL_DB_PASSWORD" -i "$LOCAL_DB_CONTAINER" \
  mysql -u "$LOCAL_DB_USER" "$LOCAL_DB_NAME" < "$DUMP_PATH"

echo "Synchronization complete. Local GLPI database now matches the server dump."

#!/bin/bash
# ==============================================================================
# GLPI Remote to Local Environment Synchronization Script
# Automatically pulls Database Dump & Configurations from GLPI Server (192.168.1.189)
# ==============================================================================

SERVER_IP="192.168.1.189"
SERVER_USER="glpiusr"
SERVER_PASS="Adming123!"
SSHPASS="/opt/homebrew/bin/sshpass"

REMOTE_DB_USER="glpiuser"
REMOTE_DB_PASS="Kinetic5mt2021"
REMOTE_DB_NAME="glpidb"

echo "========================================================"
echo "🔄 Checking connectivity to GLPI Server ($SERVER_IP)..."
echo "========================================================"

if ! ping -c 1 -W 2 $SERVER_IP > /dev/null 2>&1; then
  echo "❌ Error: Unable to reach server at $SERVER_IP."
  echo "   Please check network connection or VPN."
  exit 1
fi

echo "✅ Server reachable! Fetching remote database dump (7.3MB)..."

# 1. Dump database remotely and download
$SSHPASS -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" \
  "mysqldump -h 127.0.0.1 -u $REMOTE_DB_USER -p'$REMOTE_DB_PASS' $REMOTE_DB_NAME" > glpi_remote_dump.sql 2>/dev/null

if [ -s glpi_remote_dump.sql ]; then
  echo "✅ Database dump downloaded successfully (glpi_remote_dump.sql)."
  echo "📥 Restoring database into local Docker container (glpi_db)..."
  docker exec -i glpi_db mysql -u glpi -pglpi_password glpidb < glpi_remote_dump.sql
  echo "🎉 Local database updated to match server!"
else
  echo "⚠️ Warning: Database dump failed or empty."
  exit 1
fi

echo "========================================================"
echo "✨ Synchronization Complete! Local GLPI database matches server."
echo "========================================================"

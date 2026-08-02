"""
GLPI to Google Sheets & AppSheet Synchronization Service.

Main entry point orchestrating data retrieval from GLPI REST API and updating
Google Sheets (AppSheet backend) or executing direct AppSheet Inbound REST API actions.
"""

import sys
import os
import argparse
import logging
from typing import List, Dict, Any, Tuple
from dotenv import load_dotenv

from glpi_client import GLPIClient, GLPIClientError
from sheets_client import GoogleSheetsClient, GoogleSheetsClientError
from appsheet_client import AppSheetClient, AppSheetClientError


def configure_logging(log_level_str: str):
    """Setup application logging configuration."""
    level = getattr(logging, log_level_str.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )


def transform_glpi_tickets(tickets: List[Dict[str, Any]]) -> Tuple[List[str], List[List[Any]], List[Dict[str, Any]]]:
    """
    Transform GLPI ticket items into Google Sheets rows and AppSheet row dictionaries.

    :param tickets: Raw ticket list from GLPI REST API
    :return: Tuple of (headers, sheets_rows, appsheet_rows)
    """
    headers = [
        "Ticket ID",
        "Title",
        "Status",
        "Priority",
        "Date Created",
        "Date Modified",
        "Description"
    ]

    sheets_rows = []
    appsheet_rows = []

    for ticket in tickets:
        ticket_id = str(ticket.get("id", ""))
        title = str(ticket.get("name", ""))
        status = str(ticket.get("status", ""))
        priority = str(ticket.get("priority", ""))
        date_created = str(ticket.get("date", ""))
        date_mod = str(ticket.get("date_mod", ""))

        # Content can contain HTML tags or raw text, strip basic leading/trailing spaces
        description = str(ticket.get("content", "")).replace("\r\n", " ").replace("\n", " ").strip()
        # Truncate description for clean display if overly long
        if len(description) > 500:
            description = description[:497] + "..."

        # Google Sheets 2D row format
        sheets_rows.append([
            ticket_id,
            title,
            status,
            priority,
            date_created,
            date_mod,
            description
        ])

        # AppSheet dictionary format
        appsheet_rows.append({
            "Ticket ID": ticket_id,
            "Title": title,
            "Status": status,
            "Priority": priority,
            "Date Created": date_created,
            "Date Modified": date_mod,
            "Description": description
        })

    return headers, sheets_rows, appsheet_rows


def transform_glpi_assets(assets: List[Dict[str, Any]]) -> Tuple[List[str], List[List[Any]], List[Dict[str, Any]]]:
    """
    Transform GLPI asset items into Google Sheets rows and AppSheet row dictionaries.

    :param assets: Raw asset list from GLPI REST API
    :return: Tuple of (headers, sheets_rows, appsheet_rows)
    """
    headers = [
        "Asset ID",
        "Name",
        "Serial Number",
        "Asset Tag",
        "Contact",
        "Date Modified"
    ]

    sheets_rows = []
    appsheet_rows = []

    for asset in assets:
        asset_id = str(asset.get("id", ""))
        name = str(asset.get("name", ""))
        serial = str(asset.get("serial", ""))
        otherserial = str(asset.get("otherserial", ""))
        contact = str(asset.get("contact", ""))
        date_mod = str(asset.get("date_mod", ""))

        sheets_rows.append([
            asset_id,
            name,
            serial,
            otherserial,
            contact,
            date_mod
        ])

        appsheet_rows.append({
            "Asset ID": asset_id,
            "Name": name,
            "Serial Number": serial,
            "Asset Tag": otherserial,
            "Contact": contact,
            "Date Modified": date_mod
        })

    return headers, sheets_rows, appsheet_rows


def parse_arguments() -> argparse.Namespace:
    """Parse CLI options and flags."""
    parser = argparse.ArgumentParser(
        description="GLPI REST API to Google Sheets & AppSheet Sync Service"
    )
    parser.add_argument(
        "--mode",
        choices=["sheets", "appsheet", "both"],
        help="Sync target: 'sheets', 'appsheet', or 'both' (overrides SYNC_MODE env)"
    )
    parser.add_argument(
        "--item-type",
        default=None,
        help="GLPI Item Type to sync (e.g. 'Ticket', 'Computer') (overrides GLPI_ITEM_TYPE env)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of GLPI records to fetch (overrides FETCH_LIMIT env)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch GLPI data and process records without writing to Sheets or AppSheet"
    )
    return parser.parse_args()


def main():
    """Main orchestrator function."""
    load_dotenv()
    args = parse_arguments()

    log_level = os.getenv("LOG_LEVEL", "INFO")
    configure_logging(log_level)

    logger = logging.getLogger("sync_main")
    logger.info("Starting GLPI Synchronization Service...")

    # Load and validate configuration
    glpi_url = os.getenv("GLPI_URL")
    glpi_app_token = os.getenv("GLPI_APP_TOKEN")
    glpi_user_token = os.getenv("GLPI_USER_TOKEN")

    sync_mode = args.mode or os.getenv("SYNC_MODE", "both").lower()
    item_type = args.item_type or os.getenv("GLPI_ITEM_TYPE", "Ticket")
    fetch_limit_env = os.getenv("FETCH_LIMIT", "100")
    fetch_limit = args.limit if args.limit is not None else int(fetch_limit_env)

    # Validate essential GLPI configuration
    if not glpi_url or not glpi_app_token or not glpi_user_token:
        logger.error(
            "Missing GLPI configuration! Please set GLPI_URL, GLPI_APP_TOKEN, and GLPI_USER_TOKEN in .env file."
        )
        sys.exit(1)

    # 1. Fetch data from GLPI REST API
    logger.info(f"Connecting to GLPI at '{glpi_url}'...")
    glpi_records: List[Dict[str, Any]] = []

    try:
        with GLPIClient(glpi_url, glpi_app_token, glpi_user_token) as glpi:
            if item_type.lower() == "ticket":
                glpi_records = glpi.get_tickets(limit=fetch_limit)
            else:
                glpi_records = glpi.get_assets(itemtype=item_type, limit=fetch_limit)

    except GLPIClientError as e:
        logger.critical(f"GLPI integration failed: {e}")
        sys.exit(1)

    if not glpi_records:
        logger.warning(f"No {item_type} records returned from GLPI. Nothing to sync.")
        sys.exit(0)

    # 2. Transform records
    if item_type.lower() == "ticket":
        headers, sheets_rows, appsheet_rows = transform_glpi_tickets(glpi_records)
    else:
        headers, sheets_rows, appsheet_rows = transform_glpi_assets(glpi_records)

    logger.info(f"Transformed {len(glpi_records)} record(s) ready for synchronization.")

    if args.dry_run:
        logger.info("[DRY RUN MODE] Data processed successfully. Skipping external API calls.")
        logger.info(f"Sample transformed record: {appsheet_rows[0] if appsheet_rows else 'N/A'}")
        sys.exit(0)

    # 3. Perform Google Sheets Synchronization if enabled
    if sync_mode in ["sheets", "both"]:
        spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID")
        sheet_name = os.getenv("GOOGLE_SHEET_NAME", "Tickets")
        credentials_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

        if not spreadsheet_id or not os.path.exists(credentials_file):
            logger.error(
                f"Google Sheets config missing or credentials file '{credentials_file}' not found."
            )
        else:
            try:
                sheets_client = GoogleSheetsClient(credentials_file)
                sheets_client.sync_records(
                    spreadsheet_id=spreadsheet_id,
                    sheet_name=sheet_name,
                    headers=headers,
                    records=sheets_rows,
                    clear_existing=False
                )
                logger.info("Google Sheets synchronization completed successfully.")
            except GoogleSheetsClientError as e:
                logger.error(f"Google Sheets sync failed: {e}")

    # 4. Perform Direct AppSheet API Synchronization if enabled
    if sync_mode in ["appsheet", "both"]:
        app_id = os.getenv("APPSHEET_APP_ID")
        access_key = os.getenv("APPSHEET_ACCESS_KEY")
        table_name = os.getenv("APPSHEET_TABLE_NAME", "Tickets")

        if not app_id or not access_key:
            logger.error("AppSheet API config missing! Please set APPSHEET_APP_ID and APPSHEET_ACCESS_KEY.")
        else:
            try:
                appsheet_client = AppSheetClient(
                    app_id=app_id,
                    access_key=access_key,
                    table_name=table_name
                )
                # Use Upsert action to automatically update or insert records
                response = appsheet_client.upsert_rows(appsheet_rows)
                logger.info("AppSheet Direct API synchronization completed successfully.")
            except AppSheetClientError as e:
                logger.error(f"AppSheet API sync failed: {e}")

    logger.info("GLPI Sync Service finished successfully.")


if __name__ == "__main__":
    main()

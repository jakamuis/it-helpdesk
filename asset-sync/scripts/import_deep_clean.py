"""Quarantined historical Registration Asset GLPI importer."""

import sys


POLICY_MESSAGE = (
    "BLOCKED: Registration Asset is comparison-only; GLPI mutations must use "
    "the authoritative Datasheet workflow."
)
POLICY_EXIT_CODE = 78


def main() -> int:
    """Refuse this retired importer before loading Excel or GLPI dependencies."""
    print(POLICY_MESSAGE, file=sys.stderr)
    return POLICY_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())


# Historical implementation below. Keep it unreachable and non-dispatchable.
import asyncio
import os
import pandas as pd
import httpx
import re
import pymysql
from loguru import logger

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.services.glpi_client import GLPIClient
from app.services.sheets_client import SheetsClient
from app.core.config import settings

async def get_or_create(client, glpi, endpoint, field, value):
    if not value or str(value).lower() in ['nan', 'none', '']: return 0
    res = await client.get(f"{glpi.base_url}/search/{endpoint}", headers=glpi.headers, params={"criteria[0][field]": 1, "criteria[0][searchtype]": "equals", "criteria[0][value]": value})
    if res.status_code == 200:
        json_data = res.json()
        if isinstance(json_data, dict):
            data = json_data.get("data", [])
            if data: return data[0]["id"]
    res = await client.post(f"{glpi.base_url}/{endpoint}", headers=glpi.headers, json={"input": {field: value}})
    json_data = res.json()
    if isinstance(json_data, dict):
        return json_data.get("id", 0)
    return 0

async def _historical_registration_asset_mutation_disabled():
    raise RuntimeError(POLICY_MESSAGE)

    glpi = GLPIClient()
    excel_path = "/app/docs/Samator Registration Asset 1.0_Final_Remaining.xlsx"
    if not os.path.exists(excel_path):
        logger.error(f"Excel file not found at {excel_path}")
        return

    logger.info("Reading Google Sheets to build mapping...")
    sheets = SheetsClient()
    rows = sheets.read_all_assets(settings.SPREADSHEET_ID, settings.SHEET_NAME)
    
    akuntansi_to_am = {}
    for r in rows:
        dat = str(r.get("NO. ASSET AKUNTANSI (DAT)", "")).strip()
        am = str(r.get("QRCODE UNIT", "")).strip().upper()
        if dat and am:
            akuntansi_to_am[dat] = am

    logger.info("Reading Final Remaining Excel file...")
    df = pd.read_excel(excel_path, engine='openpyxl')
    
    matched_items = []
    
    for idx, row in df.iterrows():
        val = str(row.get('Asset /  Tag  ID', '')).strip().upper()
        cleaned = re.sub(r'[^A-Z0-9]', '', val)
        
        asset_id = None
        if cleaned.startswith('AM') or cleaned.startswith('AN'):
            digits = cleaned[2:]
            if len(digits) == 10:
                asset_id = f'AM-{digits[:3]}-{digits[3:6]}-{digits[6:]}'
        elif '23' in cleaned:
            match = re.search(r'(23\d+)', cleaned)
            if match:
                dat_num = match.group(1)
                if dat_num in akuntansi_to_am:
                    asset_id = akuntansi_to_am[dat_num]
                    
        if asset_id:
            matched_items.append((idx, asset_id))

    logger.info(f"Found {len(matched_items)} items matched after deep cleaning. Processing them now...")
    if not matched_items:
        return
        
    logger.info("Fetching GLPI inventory...")
    try:
        conn = pymysql.connect(host='glpi_db', user='glpi', password='glpi_password', database='glpidb')
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, otherserial FROM glpi_computers;")
            db_rows = cursor.fetchall()
        glpi_otherserials = {str(r[1]).strip().upper(): r[0] for r in db_rows if r[1]}
        conn.close()
    except Exception as e:
        logger.error(f"Failed to fetch from DB: {e}")
        return

    await glpi._init_session()
    async with httpx.AsyncClient() as client:
        for idx, asset_id in matched_items:
            row = df.loc[idx]
            
            comp_data = {
                "name": str(row.get("Hostname", "")).strip(),
                "contact": str(row.get("User Assignment ( Full Name )", "")).strip(),
                "serial": str(row.get("Serial Number", "")).strip(),
                "otherserial": asset_id
            }
            comp_data = {k: v for k, v in comp_data.items() if v and str(v).lower() != 'nan'}
            
            comments = []
            if str(row.get("RAM (GB)")) != "nan": comments.append(f"RAM: {row.get('RAM (GB)')} GB")
            if str(row.get("Storage")) != "nan": comments.append(f"Storage: {row.get('Storage')}")
            if str(row.get("Processor")) != "nan": comments.append(f"Processor: {row.get('Processor')}")
            if comments:
                comp_data["comment"] = " | ".join(comments)

            if asset_id in glpi_otherserials:
                comp_id = glpi_otherserials[asset_id]
                res = await client.put(f"{glpi.base_url}/Computer/{comp_id}", headers=glpi.headers, json={"input": comp_data})
                if res.status_code not in (200, 201): continue
            else:
                res = await client.post(f"{glpi.base_url}/Computer", headers=glpi.headers, json={"input": comp_data})
                if res.status_code not in (200, 201): continue
                comp_json = res.json()
                if isinstance(comp_json, dict) and "id" in comp_json:
                    comp_id = comp_json["id"]
                else: continue
                    
            os_name = str(row.get("Operating System"))
            if os_name and str(os_name).lower() != "nan":
                os_id = await get_or_create(client, glpi, "OperatingSystem", "name", str(os_name).strip())
                if os_id:
                    await client.post(f"{glpi.base_url}/Item_OperatingSystem", headers=glpi.headers, json={"input": {
                        "items_id": comp_id,
                        "itemtype": "Computer",
                        "operatingsystems_id": os_id
                    }})

    await glpi.kill_session()
    logger.info("Successfully synced all deeply cleaned codes!")

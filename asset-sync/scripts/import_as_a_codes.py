import asyncio
import os
import sys
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

async def main():
    glpi = GLPIClient()
    excel_path = "/app/docs/Samator Registration Asset 1.0_Final_Remaining.xlsx"
    if not os.path.exists(excel_path):
        logger.error(f"Excel file not found at {excel_path}")
        return

    logger.info("Reading Google Sheets to build mapping...")
    sheets = SheetsClient()
    rows = sheets.read_all_assets(settings.SPREADSHEET_ID, settings.SHEET_NAME)
    
    # Map NO. ASSET AKUNTANSI (DAT) to QRCODE UNIT
    akuntansi_to_am = {}
    for r in rows:
        dat = str(r.get("NO. ASSET AKUNTANSI (DAT)", "")).strip()
        am = str(r.get("QRCODE UNIT", "")).strip().upper()
        if dat and am:
            akuntansi_to_am[dat] = am

    logger.info("Reading Final Remaining Excel file...")
    df = pd.read_excel(excel_path, engine='openpyxl')
    
    pattern = re.compile(r'^AS\d+A$')
    matched_items = []
    
    for idx, row in df.iterrows():
        val = str(row.get('Asset /  Tag  ID', '')).strip().upper()
        if pattern.match(val):
            stripped = val[2:-1]
            if stripped in akuntansi_to_am:
                am_code = akuntansi_to_am[stripped]
                matched_items.append((idx, am_code))

    logger.info(f"Found {len(matched_items)} AS...A items matched to Google Sheets. Processing them now...")
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
                # Update existing
                comp_id = glpi_otherserials[asset_id]
                res = await client.put(f"{glpi.base_url}/Computer/{comp_id}", headers=glpi.headers, json={"input": comp_data})
                if res.status_code not in (200, 201):
                    logger.error(f"Failed to update {asset_id}: {res.text}")
                    continue
            else:
                # Create new
                res = await client.post(f"{glpi.base_url}/Computer", headers=glpi.headers, json={"input": comp_data})
                if res.status_code not in (200, 201):
                    logger.error(f"Failed to create {asset_id}: {res.text}")
                    continue
                comp_json = res.json()
                if isinstance(comp_json, dict) and "id" in comp_json:
                    comp_id = comp_json["id"]
                else:
                    continue
                    
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
    logger.info("Successfully synced all matched AS...A codes!")

if __name__ == "__main__":
    asyncio.run(main())

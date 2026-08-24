"""Quarantined historical Registration Asset splitter/importer."""

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
import pymysql
from loguru import logger

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.services.glpi_client import GLPIClient
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
    excel_path = "/app/docs/Samator Registration Asset 1.0.xlsx"
    if not os.path.exists(excel_path):
        logger.error(f"Excel file not found at {excel_path}")
        return

    logger.info("Reading Excel file...")
    df = pd.read_excel(excel_path, engine='openpyxl')
    
    logger.info("Fetching GLPI inventory from database...")
    try:
        conn = pymysql.connect(host='glpi_db', user='glpi', password='glpi_password', database='glpidb')
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, otherserial FROM glpi_computers WHERE otherserial IS NOT NULL AND otherserial != '';")
            rows = cursor.fetchall()
        glpi_assets = {r[1].strip(): r[0] for r in rows}
        conn.close()
    except Exception as e:
        logger.error(f"Failed to fetch from DB: {e}")
        return

    submitted_indices = []
    remaining_indices = []

    for idx, row in df.iterrows():
        asset_id = None
        for col in df.columns:
            val = str(row.get(col)).strip()
            if val.startswith('AM-'):
                asset_id = val
                break
        
        if asset_id and asset_id in glpi_assets:
            submitted_indices.append(idx)
        else:
            remaining_indices.append(idx)

    # 1. SPLIT DATA
    df_submitted = df.loc[submitted_indices]
    df_remaining = df.loc[remaining_indices]
    
    out_dir = "/app/docs"
    submitted_path = os.path.join(out_dir, "Samator Registration Asset 1.0_Submitted.xlsx")
    remaining_path = os.path.join(out_dir, "Samator Registration Asset 1.0_Remaining.xlsx")
    
    df_submitted.to_excel(submitted_path, index=False)
    df_remaining.to_excel(remaining_path, index=False)
    logger.info(f"Saved {len(df_submitted)} rows to {submitted_path}")
    logger.info(f"Saved {len(df_remaining)} rows to {remaining_path}")

    # 2. IMPORT REMAINING
    logger.info("Importing remaining assets as NEW computers in GLPI...")
    await glpi._init_session()
    async with httpx.AsyncClient() as client:
        for idx, row in df_remaining.iterrows():
            comp_data = {
                "name": str(row.get("Hostname", "")).strip(),
                "contact": str(row.get("User Assignment ( Full Name )", "")).strip(),
                "serial": str(row.get("Serial Number", "")).strip(),
                "otherserial": str(row.get("Asset /  Tag  ID", "")).strip(),
            }
            # Handle NaNs
            comp_data = {k: v for k, v in comp_data.items() if v and v.lower() != 'nan'}
            
            # Add hardware details to comments
            comments = []
            ram = str(row.get("RAM (GB)", ""))
            storage = str(row.get("Storage", ""))
            cpu = str(row.get("Processor", ""))
            if ram and ram.lower() != 'nan': comments.append(f"RAM: {ram} GB")
            if storage and storage.lower() != 'nan': comments.append(f"Storage: {storage}")
            if cpu and cpu.lower() != 'nan': comments.append(f"Processor: {cpu}")
            if comments:
                comp_data["comment"] = " | ".join(comments)

            # Create Computer
            res = await client.post(f"{glpi.base_url}/Computer", headers=glpi.headers, json={"input": comp_data})
            if res.status_code not in (200, 201):
                logger.error(f"Failed to create computer: {res.text}")
                continue
            
            comp_json = res.json()
            if isinstance(comp_json, dict) and "id" in comp_json:
                comp_id = comp_json["id"]
                
                # Create OS Link
                os_name = str(row.get("Operating System", ""))
                if os_name and os_name.lower() != 'nan':
                    os_id = await get_or_create(client, glpi, "OperatingSystem", "name", os_name.strip())
                    if os_id:
                        await client.post(f"{glpi.base_url}/Item_OperatingSystem", headers=glpi.headers, json={"input": {
                            "items_id": comp_id,
                            "itemtype": "Computer",
                            "operatingsystems_id": os_id
                        }})
    
    await glpi.kill_session()
    logger.info("Import completed!")

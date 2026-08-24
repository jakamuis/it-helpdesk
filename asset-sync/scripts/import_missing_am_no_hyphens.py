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

    logger.info("Reading Final Remaining Excel file...")
    df = pd.read_excel(excel_path, engine='openpyxl')
    
    pattern = re.compile(r'^AM\d{10}$')
    missing_to_create = []
    
    for idx, row in df.iterrows():
        val = str(row.get('Asset /  Tag  ID', '')).strip().upper()
        if pattern.match(val):
            formatted_id = f"AM-{val[2:5]}-{val[5:8]}-{val[8:]}"
            missing_to_create.append((idx, formatted_id))

    logger.info(f"Found {len(missing_to_create)} AM codes without hyphens. Creating them now...")
    if not missing_to_create:
        return

    await glpi._init_session()
    async with httpx.AsyncClient() as client:
        for idx, asset_id in missing_to_create:
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

            res = await client.post(f"{glpi.base_url}/Computer", headers=glpi.headers, json={"input": comp_data})
            if res.status_code not in (200, 201):
                logger.error(f"Failed to create {asset_id}: {res.text}")
                continue
            
            comp_json = res.json()
            if isinstance(comp_json, dict) and "id" in comp_json:
                comp_id = comp_json["id"]
                    
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
    logger.info("Successfully created and synced all AM codes without hyphens!")

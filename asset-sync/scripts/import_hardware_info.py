import asyncio
import os
import sys
import pandas as pd
import httpx
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

async def main():
    glpi = GLPIClient()
    excel_path = "/app/docs/Samator Registration Asset 1.0_Remaining.xlsx"
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
        glpi_assets = {str(r[1]).strip().lower(): r[0] for r in rows}
        conn.close()
    except Exception as e:
        logger.error(f"Failed to fetch from DB: {e}")
        return

    matched = []
    
    for idx, row in df.iterrows():
        asset_id = None
        for col in df.columns:
            val = str(row.get(col)).strip()
            if val.lower().startswith('am-'):
                asset_id = val.lower()
                break
                
        if asset_id and asset_id in glpi_assets:
            matched.append((idx, glpi_assets[asset_id]))

    logger.info(f"Total newly matched AM- codes: {len(matched)}")
    if not matched:
        return

    await glpi._init_session()
    async with httpx.AsyncClient() as client:
        for idx, comp_id in matched:
            row = df.loc[idx]
            
            comp_data = {}
            if str(row.get("Hostname")) != "nan": comp_data["name"] = str(row.get("Hostname")).strip()
            if str(row.get("User Assignment ( Full Name )")) != "nan": comp_data["contact"] = str(row.get("User Assignment ( Full Name )")).strip()
            if str(row.get("Serial Number")) != "nan": comp_data["serial"] = str(row.get("Serial Number")).strip()
            
            comments = []
            if str(row.get("RAM (GB)")) != "nan": comments.append(f"RAM: {row.get('RAM (GB)')} GB")
            if str(row.get("Storage")) != "nan": comments.append(f"Storage: {row.get('Storage')}")
            if str(row.get("Processor")) != "nan": comments.append(f"Processor: {row.get('Processor')}")
            
            if comments:
                comp_data["comment"] = " | ".join(comments)

            if comp_data:
                await client.put(f"{glpi.base_url}/Computer/{comp_id}", headers=glpi.headers, json={"input": comp_data})
                    
            os_name = str(row.get("Operating System"))
            if os_name and os_name != "nan":
                os_id = await get_or_create(client, glpi, "OperatingSystem", "name", os_name.strip())
                if os_id:
                    await client.post(f"{glpi.base_url}/Item_OperatingSystem", headers=glpi.headers, json={"input": {
                        "items_id": comp_id,
                        "itemtype": "Computer",
                        "operatingsystems_id": os_id
                    }})

    await glpi.kill_session()
    logger.info("Hardware sync for AM- matched assets completed successfully.")

if __name__ == "__main__":
    asyncio.run(main())

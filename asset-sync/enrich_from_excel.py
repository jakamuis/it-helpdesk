"""Quarantined historical Registration Asset enrichment script.

The Registration Asset workbook is comparison-only.  The authoritative asset
source is the Datasheet, so this file intentionally has no mutating entrypoint.
The historical implementation remains below for audit/code archaeology.
"""

import sys


POLICY_MESSAGE = (
    "BLOCKED: Registration Asset is comparison-only; asset updates must use "
    "the authoritative Datasheet workflow."
)
POLICY_EXIT_CODE = 78


def main() -> int:
    """Refuse the retired enricher without loading Excel or GLPI dependencies."""
    print(POLICY_MESSAGE, file=sys.stderr)
    return POLICY_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())


# Historical implementation below.  Keep it unreachable and non-dispatchable.
import asyncio

import httpx
import pandas as pd
from loguru import logger

from app.services.glpi_client import GLPIClient

def clean_string(val):
    if pd.isna(val):
        return ""
    return str(val).strip()

async def _historical_registration_asset_enrichment_disabled():
    raise RuntimeError(POLICY_MESSAGE)

    glpi = GLPIClient()
    # Handle docker internal host resolving for local script run
    glpi.base_url = glpi.base_url.replace("host.docker.internal", "localhost")
    await glpi._ensure_session()
    
    logger.info("Fetching all Computers and Infocoms from GLPI for matching index...")
    glpi_assets = {}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Get Computers
        start = 0
        while True:
            res = await client.get(f"{glpi.base_url}/Computer?range={start}-{start+1000}", headers=glpi.headers)
            if res.status_code not in [200, 206]: break
            data = res.json()
            if not data: break
            for item in data:
                cid = item.get("id")
                glpi_assets[cid] = {
                    "id": cid,
                    "immo": set(),
                    "otherserial": str(item.get("otherserial", "")).strip(),
                    "name": str(item.get("name", "")).strip(),
                    "comment": str(item.get("comment", "")).strip(),
                }
            if len(data) < 1000: break
            start += 1000
            
        # Get Infocoms
        start = 0
        while True:
            res = await client.get(f"{glpi.base_url}/Infocom?range={start}-{start+1000}", headers=glpi.headers)
            if res.status_code not in [200, 206]: break
            data = res.json()
            if not data: break
            for item in data:
                cid = item.get("items_id")
                if cid in glpi_assets:
                    immo = str(item.get("immo_number", "")).strip()
                    if immo: glpi_assets[cid]["immo"].add(immo)
            if len(data) < 1000: break
            start += 1000

    # Build reverse indexes
    idx_immo = {}
    idx_otherserial = {}
    for cid, asset in glpi_assets.items():
        if asset["otherserial"]:
            idx_otherserial[asset["otherserial"].lower()] = cid
        for immo in asset["immo"]:
            idx_immo[immo.lower()] = cid
            cleaned_immo = "".join([c for c in immo if c.isdigit()])
            if cleaned_immo: idx_immo[cleaned_immo] = cid

    logger.info("Loading Excel file...")
    file_path = "../docs/Samator Registration Asset 1.0.xlsx"
    df = pd.read_excel(file_path, sheet_name="Form Responses 1")
    
    total = 0
    matched = 0
    
    for _, row in df.iterrows():
        asset_id = clean_string(row.get("Asset /  Tag  ID"))
        if not asset_id or asset_id.lower() == "nan": continue
        total += 1
        
        cid = None
        
        # 1. Exact match in Immobilization Number or QR Code
        search_id = asset_id.lower()
        if search_id in idx_immo:
            cid = idx_immo[search_id]
        elif search_id in idx_otherserial:
            cid = idx_otherserial[search_id]
            
        # 2. Cleaned match (digits only) for Immo Number
        if not cid:
            cleaned = "".join([c for c in search_id if c.isdigit()])
            if cleaned and cleaned in idx_immo:
                cid = idx_immo[cleaned]
                
        if cid:
            matched += 1
            # --- Perform Enrichment ---
            hostname = clean_string(row.get("Hostname"))
            serial = clean_string(row.get("Serial Number"))
            user = clean_string(row.get("User Assignment ( Full Name )"))
            mac = clean_string(row.get("MAC Address"))
            kaspersky = clean_string(row.get("Is Kaspersky AV installed ?"))
            domain = clean_string(row.get("Is join domain done?"))
            notes = clean_string(row.get("Notes"))
            dept = clean_string(row.get("Department"))
            
            # Prepare update payload for Computer
            update_data = {}
            if hostname and hostname.lower() != "nan":
                update_data["name"] = hostname
            if serial and serial.lower() != "nan":
                update_data["serial"] = serial
            if user and user.lower() != "nan":
                update_data["contact"] = user
                
            # Build new comment
            existing_comment = glpi_assets[cid]["comment"]
            new_comment_parts = []
            if dept and dept.lower() != "nan": new_comment_parts.append(f"Department: {dept}")
            if mac and mac.lower() != "nan": new_comment_parts.append(f"MAC: {mac}")
            if domain and domain.lower() != "nan": new_comment_parts.append(f"Domain Joined: {domain}")
            if kaspersky and kaspersky.lower() != "nan": new_comment_parts.append(f"Kaspersky: {kaspersky}")
            if notes and notes.lower() != "nan": new_comment_parts.append(f"Notes: {notes}")
            
            if new_comment_parts:
                additional_info = " | ".join(new_comment_parts)
                if additional_info not in existing_comment:
                    # GLPI comments can be updated directly
                    update_data["comment"] = existing_comment + "\n\n[AD Migration Data]\n" + additional_info
            
            if update_data:
                try:
                    await glpi.update_asset(cid, update_data)
                    logger.info(f"Enriched GLPI ID {cid} (Matched {asset_id})")
                except Exception as e:
                    logger.error(f"Failed to enrich GLPI ID {cid}: {e}")
            
            # Components Mapping
            cpu = clean_string(row.get("Processor"))
            ram = clean_string(row.get("RAM (GB)"))
            storage = clean_string(row.get("Storage"))
            os_val = clean_string(row.get("Operating System"))
            
            if cpu and cpu.lower() != "nan":
                cpu_id = await glpi.get_or_create_dropdown("DeviceProcessor", cpu, allow_create=True)
                if cpu_id: await glpi.link_component("Item_DeviceProcessor", "deviceprocessors_id", cid, cpu_id)
            if ram and ram.lower() != "nan":
                ram_str = f"{ram} GB" if str(ram).isdigit() else ram
                ram_id = await glpi.get_or_create_dropdown("DeviceMemory", ram_str, allow_create=True)
                if ram_id: await glpi.link_component("Item_DeviceMemory", "devicememories_id", cid, ram_id)
            if storage and storage.lower() != "nan":
                storage_id = await glpi.get_or_create_dropdown("DeviceHardDrive", storage, allow_create=True)
                if storage_id: await glpi.link_component("Item_DeviceHardDrive", "deviceharddrives_id", cid, storage_id)
            if os_val and os_val.lower() != "nan":
                os_id = await glpi.get_or_create_dropdown("OperatingSystem", os_val, allow_create=True)
                if os_id: await glpi.link_component("Item_OperatingSystem", "operatingsystems_id", cid, os_id)
                
    logger.info(f"Finished enrichment. Processed {total} valid rows in Excel.")
    logger.info(f"Successfully matched and enriched: {matched} assets.")
    await glpi.kill_session()

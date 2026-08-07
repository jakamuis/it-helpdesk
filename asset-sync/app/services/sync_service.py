import time
from loguru import logger
from app.schemas.asset import AssetSyncRequest, AssetSyncResponse
from app.services.glpi_client import GLPIClient, GLPIClientError
from app.repository.audit import AuditRepository

class SyncService:
    def __init__(self, glpi_client: GLPIClient, audit_repo: AuditRepository):
        self.glpi = glpi_client
        self.audit = audit_repo

    async def _map_payload(self, req: AssetSyncRequest) -> dict:
        data = {
            "otherserial": req.qrcode,
            "entities_id": 0 # Default entity
        }
        
        # Name: mapped from SUB KATEGORI 1. If empty, compose from Brand and Model
        if req.name:
            data["name"] = req.name
        else:
            brand_part = req.brand if req.brand else ""
            model_part = req.model if req.model else ""
            composed = f"{brand_part} {model_part}".strip()
            data["name"] = composed if composed else req.qrcode
            
        if req.user:
            data["contact"] = req.user
            
        if req.comment:
            data["comment"] = req.comment
            
        # --- Auto-Provisioning Dropdowns ---
        if req.brand:
            data["manufacturers_id"] = await self.glpi.get_or_create_dropdown("Manufacturer", req.brand)
            
        if req.model:
            model_itemtype = "MonitorModel" if req.asset_type == "Monitor" else "ComputerModel"
            model_key = "monitormodels_id" if req.asset_type == "Monitor" else "computermodels_id"
            data[model_key] = await self.glpi.get_or_create_dropdown(model_itemtype, req.model)
            
        if req.location:
            data["locations_id"] = await self.glpi.get_or_create_dropdown("Location", req.location, allow_create=False)
            
        if req.status:
            data["states_id"] = await self.glpi.get_or_create_dropdown("State", req.status, allow_create=False)
            
        if req.category:
            type_itemtype = "MonitorType" if req.asset_type == "Monitor" else "ComputerType"
            type_key = "monitortypes_id" if req.asset_type == "Monitor" else "computertypes_id"
            data[type_key] = await self.glpi.get_or_create_dropdown(type_itemtype, req.category, allow_create=False)

        return {k: v for k, v in data.items() if v is not None}

    async def process_sync(self, req: AssetSyncRequest) -> AssetSyncResponse:
        start_time = time.time()
        status = "FAILED"
        action = "UNKNOWN"
        glpi_id = None
        error_msg = None
        
        try:
            # 1. Map payload
            glpi_data = await self._map_payload(req)
            
            # 2. Search for existing asset
            existing_asset = await self.glpi.search_asset(req.qrcode, field_id=6, itemtype=req.asset_type)
            if not existing_asset and req.name:
                existing_asset = await self.glpi.search_asset(req.name, field_id=1, itemtype=req.asset_type)
            
            if existing_asset:
                action = "UPDATE"
                glpi_id = existing_asset.get("id")
                # 3a. Update
                await self.glpi.update_asset(glpi_id, glpi_data, itemtype=req.asset_type)
                status = "SUCCESS"
                logger.info(f"Successfully updated asset {req.qrcode} (GLPI ID: {glpi_id})")
                response = AssetSyncResponse(status="updated", glpi_id=glpi_id)
            else:
                action = "CREATE"
                # 3b. Create
                glpi_id = await self.glpi.create_asset(glpi_data, itemtype=req.asset_type)
                status = "SUCCESS"
                logger.info(f"Successfully created asset {req.qrcode} (GLPI ID: {glpi_id})")
                response = AssetSyncResponse(status="created", glpi_id=glpi_id)
            # --- Infocom / Financial Data Sync ---
            if glpi_id and (req.buy_date or req.value or req.amortization or req.dat_number):
                infocom_data = {
                    "itemtype": req.asset_type,
                    "items_id": glpi_id
                }
                
                # We need to map string from Google Sheets to float/number for value, if possible
                try:
                    if req.dat_number:
                        infocom_data["immo_number"] = req.dat_number
                    if req.buy_date:
                        infocom_data["buy_date"] = req.buy_date
                    if req.value:
                        # Clean up formatting like Rp, commas, dots
                        val_str = str(req.value).replace("Rp", "").replace(".", "").replace(",", ".").strip()
                        if val_str:
                            infocom_data["value"] = float(val_str)
                    if req.amortization:
                        # Depends on what penyusutan holds, if it's duration (years), we map to amortization_time
                        infocom_data["amortization_type"] = 2 # Usually 2 is linear
                        amort_str = str(req.amortization).replace(" Tahun", "").replace(" tahun", "").strip()
                        if amort_str.isdigit():
                            infocom_data["amortization_time"] = int(amort_str)
                except Exception as eval_e:
                    logger.warning(f"Failed to parse financial data for {req.qrcode}: {eval_e}")

                # Search if infocom exists
                existing_infocom_id = await self.glpi.search_infocom("Computer", glpi_id)
                if existing_infocom_id:
                    await self.glpi.update_infocom(existing_infocom_id, infocom_data)
                    logger.info(f"Updated Infocom for GLPI ID: {glpi_id}")
                else:
                    await self.glpi.create_infocom(infocom_data)
                    logger.info(f"Created Infocom for GLPI ID: {glpi_id}")

            # --- Native Components ---
            if glpi_id and req.asset_type != "Monitor":
                if req.cpu:
                    cpu_id = await self.glpi.get_or_create_dropdown("DeviceProcessor", req.cpu, allow_create=True)
                    if cpu_id:
                        await self.glpi.link_component("Item_DeviceProcessor", "deviceprocessors_id", glpi_id, cpu_id)
                        
                if req.ram:
                    ram_id = await self.glpi.get_or_create_dropdown("DeviceMemory", req.ram, allow_create=True)
                    if ram_id:
                        await self.glpi.link_component("Item_DeviceMemory", "devicememories_id", glpi_id, ram_id)
                        
                if req.os:
                    os_id = await self.glpi.get_or_create_dropdown("OperatingSystem", req.os, allow_create=True)
                    if os_id:
                        await self.glpi.link_component("Item_OperatingSystem", "operatingsystems_id", glpi_id, os_id)
                        
                if req.storage:
                    storage_id = await self.glpi.get_or_create_dropdown("DeviceHardDrive", req.storage, allow_create=True)
                    if storage_id:
                        await self.glpi.link_component("Item_DeviceHardDrive", "deviceharddrives_id", glpi_id, storage_id)
                        
                if getattr(req, "monitor", None):
                    await self.glpi.link_monitor(glpi_id, req.monitor)
                
        except GLPIClientError as e:
            action = "FAILED" if action == "UNKNOWN" else action
            error_msg = str(e)
            logger.error(f"GLPI sync failed for {req.qrcode}: {error_msg}")
            response = AssetSyncResponse(status="error", message=error_msg)
        except Exception as e:
            action = "FAILED" if action == "UNKNOWN" else action
            error_msg = str(e)
            logger.exception(f"Unexpected error syncing {req.qrcode}: {error_msg}")
            response = AssetSyncResponse(status="error", message="Internal sync error")
            
        finally:
            # 4. Log to audit database
            duration = time.time() - start_time
            await self.audit.log_sync(
                qrcode=req.qrcode,
                action=action,
                status=status,
                duration=duration,
                glpi_id=glpi_id,
                request_payload=req.model_dump(),
                response_payload=response.model_dump(),
                error=error_msg
            )
            # Ensure GLPI session is killed or returned to pool
            await self.glpi.kill_session()
            
        return response

    async def run_batch_sync(self):
        from app.services.sheets_client import SheetsClient
        from app.services.excel_client import ExcelClient
        from app.core.config import settings
        
        logger.info("Starting scheduled batch sync from Google Sheets...")
        
        try:
            sheets = SheetsClient()
            rows = sheets.read_all_assets(settings.SPREADSHEET_ID, settings.SHEET_NAME)
            
            excel = ExcelClient()
            specs_map = excel.load_specs_data()
        except Exception as e:
            logger.error(f"Batch sync failed to read data sources: {e}")
            return
            
        logger.info(f"Fetched {len(rows)} rows from Google Sheets. Processing...")
        
        for row in rows:
            # According to our get_headers script output
            qrcode = row.get("QRCODE UNIT")
            if not qrcode:
                continue
                
            # Filter exactly as requested:
            # Column G (KATEGORI ASSET) = elektronik
            # Column H (SUB KATEGORI 1) = Komputer
            # Column I (SUB KATEGORI 2) = CPU or laptop
            kategori = str(row.get("KATEGORI ASSET") or "").strip().lower()
            sub1 = str(row.get("SUB KATEGORI 1") or "").strip().lower()
            sub2 = str(row.get("SUB KATEGORI 2") or "").strip().lower()
            
            if kategori != "elektronik":
                continue
                
            # Allow cases where sub1="komputer" and sub2="cpu"/"laptop"
            # AND allow cases where sub1="laptop" or sub1="cpu" directly
            # AND allow "monitor" for standalone monitor assets
            is_valid = False
            asset_type = "Computer"
            
            if sub1 == "komputer" and sub2 in ["cpu", "laptop"]:
                is_valid = True
            elif sub1 in ["cpu", "laptop"]:
                is_valid = True
            elif sub2 == "monitor" or sub1 == "monitor":
                is_valid = True
                asset_type = "Monitor"
                
            if not is_valid:
                continue
                
            # Build location from Wilayah, Cabang, Area (excluding LOKASI/coordinates)
            loc_parts = [
                row.get("WILAYAH"), 
                row.get("CABANG"), 
                row.get("AREA")
            ]
            # Filter empty strings and join
            loc_str = " > ".join([str(p) for p in loc_parts if p])
            
            # Format TAHUN PEROLEHAN
            tahun = str(row.get("TAHUN PEROLEHAN") or "").strip()
            buy_date = None
            if tahun:
                if len(tahun) == 4 and tahun.isdigit():
                    buy_date = f"{tahun}-01-01"
                else:
                    # If it's already a date format, try to use it directly, else fallback or ignore
                    buy_date = tahun
                
            # Extract specs if available
            specs = specs_map.get(qrcode, {})
            
            req = AssetSyncRequest(
                qrcode=qrcode,
                name=row.get("SUB KATEGORI 1"),
                dat_number=row.get("NO. ASSET AKUNTANSI (DAT)"),
                asset_type=asset_type,
                brand=row.get("MERK"),
                model=row.get("TYPE"),
                category=row.get("JENIS ASSET"),
                location=loc_str,
                status=row.get("KONDISI"),
                user=row.get("NAMA USER"),
                comment=row.get("KETERANGAN"),
                buy_date=buy_date,
                value=row.get("NILAI RUPIAH"),
                amortization=row.get("PENYUSUTAN"),
                cpu=specs.get("cpu"),
                ram=specs.get("ram"),
                storage=specs.get("storage"),
                os=specs.get("os"),
                mac=specs.get("mac"),
                monitor=str(specs.get("Monitor") or "")
            )
            
            await self.process_sync(req)
            
        logger.info("Scheduled batch sync completed.")

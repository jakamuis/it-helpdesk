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
        
        # Name: If NO. ASSET AKUNTANSI is empty, compose from Brand and Model
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
            data["computermodels_id"] = await self.glpi.get_or_create_dropdown("ComputerModel", req.model)
            
        if req.location:
            data["locations_id"] = await self.glpi.get_or_create_dropdown("Location", req.location)
            
        if req.status:
            data["states_id"] = await self.glpi.get_or_create_dropdown("State", req.status)
            
        if req.category:
            data["computertypes_id"] = await self.glpi.get_or_create_dropdown("ComputerType", req.category)

        return data

    async def process_sync(self, req: AssetSyncRequest) -> AssetSyncResponse:
        start_time = time.time()
        glpi_id = None
        action = "UNKNOWN"
        status = "ERROR"
        error_msg = None
        
        try:
            # 1. Map payload (now async because of auto-provisioning lookups)
            glpi_data = await self._map_payload(req)
            
            # 2. Search for existing asset
            existing_asset = await self.glpi.search_asset(req.qrcode)
            
            if existing_asset:
                action = "UPDATE"
                glpi_id = existing_asset.get("id")
                # 3a. Update
                await self.glpi.update_asset(glpi_id, glpi_data)
                status = "SUCCESS"
                logger.info(f"Successfully updated asset {req.qrcode} (GLPI ID: {glpi_id})")
                response = AssetSyncResponse(status="updated", glpi_id=glpi_id)
            else:
                action = "CREATE"
                # 3b. Create
                glpi_id = await self.glpi.create_asset(glpi_data)
                status = "SUCCESS"
                logger.info(f"Successfully created asset {req.qrcode} (GLPI ID: {glpi_id})")
                response = AssetSyncResponse(status="created", glpi_id=glpi_id)
                
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
        from app.core.config import settings
        
        logger.info("Starting scheduled batch sync from Google Sheets...")
        
        try:
            sheets = SheetsClient()
            rows = sheets.read_all_assets(settings.SPREADSHEET_ID, settings.SHEET_NAME)
        except Exception as e:
            logger.error(f"Batch sync failed to read sheets: {e}")
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
            is_valid = False
            if sub1 == "komputer" and sub2 in ["cpu", "laptop"]:
                is_valid = True
            elif sub1 in ["cpu", "laptop"]:
                is_valid = True
                
            if not is_valid:
                continue
                
            # Compose comment with remaining fields
            comments_parts = []
            if row.get("KETERANGAN"): comments_parts.append(f"KETERANGAN: {row.get('KETERANGAN')}")
            if row.get("KAPASITAS"): comments_parts.append(f"KAPASITAS: {row.get('KAPASITAS')}")
            if row.get("WARNA"): comments_parts.append(f"WARNA: {row.get('WARNA')}")
            if row.get("TAHUN PEROLEHAN"): comments_parts.append(f"TAHUN PEROLEHAN: {row.get('TAHUN PEROLEHAN')}")
            
            # Build location from Wilayah, Cabang, Area (excluding LOKASI/coordinates)
            loc_parts = [
                row.get("WILAYAH"), 
                row.get("CABANG"), 
                row.get("AREA")
            ]
            # Filter empty strings and join
            loc_str = " > ".join([str(p) for p in loc_parts if p])
                
            req = AssetSyncRequest(
                qrcode=qrcode,
                name=row.get("NO. ASSET AKUNTANSI (DAT)"),
                brand=row.get("MERK"),
                model=row.get("TYPE"),
                category=row.get("JENIS ASSET"),
                location=loc_str,
                status=row.get("KONDISI"),
                user=row.get("NAMA USER"),
                comment=" | ".join(comments_parts) if comments_parts else None
            )
            
            await self.process_sync(req)
            
        logger.info("Scheduled batch sync completed.")

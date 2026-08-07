from pydantic import BaseModel, Field
from typing import Optional, Union

class AssetSyncRequest(BaseModel):
    # Core identifying fields
    qrcode: str = Field(..., description="QRCODE UNIT (Primary Key)")
    name: Optional[str] = Field(None, description="GLPI Name (from SUB KATEGORI 1)")
    dat_number: Optional[str] = Field(None, description="NO. ASSET AKUNTANSI (DAT)")
    asset_type: str = Field(..., description="Asset Type (Computer or Monitor)")
    
    # Dropdown references (string values that will be mapped to IDs)
    brand: Optional[str] = Field(None, description="MERK")
    model: Optional[str] = Field(None, description="TYPE")
    category: Optional[str] = Field(None, description="JENIS ASSET")
    location: Optional[str] = Field(None, description="LOKASI / WILAYAH / CABANG")
    status: Optional[str] = Field(None, description="KONDISI")
    
    # Other standard fields
    user: Optional[str] = Field(None, description="NAMA USER")
    comment: Optional[str] = Field(None, description="KETERANGAN")
    
    # Financial fields (Infocom)
    buy_date: Optional[str] = Field(None, description="Tahun Perolehan mapped to buy_date")
    value: Optional[Union[int, float, str]] = Field(None, description="Nilai Rupiah mapped to value")
    amortization: Optional[str] = Field(None, description="Penyusutan mapped to amortization_time")
    
    # --- Extracted Specs (From Excel) ---
    cpu: Optional[str] = Field(None, description="Processor")
    ram: Optional[str] = Field(None, description="RAM (GB)")
    storage: Optional[str] = Field(None, description="Storage")
    monitor: Optional[str] = Field(None, description="Monitor")
    os: Optional[str] = Field(None, description="Operating System")
    mac: Optional[str] = Field(None, description="MAC Address")

class AssetSyncResponse(BaseModel):
    status: str
    glpi_id: Optional[int] = None
    message: Optional[str] = None

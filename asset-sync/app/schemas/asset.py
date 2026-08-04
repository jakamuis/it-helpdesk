from pydantic import BaseModel, Field
from typing import Optional

class AssetSyncRequest(BaseModel):
    # Core identifying fields
    qrcode: str = Field(..., description="QRCODE UNIT (Primary Key)")
    name: Optional[str] = Field(None, description="NO. ASSET AKUNTANSI (DAT)")
    
    # Dropdown references (string values that will be mapped to IDs)
    brand: Optional[str] = Field(None, description="MERK")
    model: Optional[str] = Field(None, description="TYPE")
    category: Optional[str] = Field(None, description="JENIS ASSET")
    location: Optional[str] = Field(None, description="LOKASI / WILAYAH / CABANG")
    status: Optional[str] = Field(None, description="KONDISI")
    
    # Other standard fields
    user: Optional[str] = Field(None, description="NAMA USER")
    comment: Optional[str] = Field(None, description="Combined fields like KETERANGAN, KAPASITAS, dll")

class AssetSyncResponse(BaseModel):
    status: str
    glpi_id: Optional[int] = None
    message: Optional[str] = None

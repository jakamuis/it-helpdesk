from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

class AssetSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # Core identifying fields
    qrcode: str = Field(..., min_length=1, description="QRCODE UNIT (Primary Key)")
    name: Optional[str] = Field(None, description="GLPI Name (from SUB KATEGORI 1)")
    dat_number: Optional[str] = Field(None, description="NO. ASSET AKUNTANSI (DAT)")
    asset_type: Literal["Computer", "Monitor"] = Field(..., description="GLPI asset type")
    
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
    amortization: Optional[str] = Field(None, description="PENYUSUTAN mapped to GLPI sink_time")
    
class AssetSyncResponse(BaseModel):
    status: str
    glpi_id: Optional[int] = None
    message: Optional[str] = None
    dry_run: bool = False

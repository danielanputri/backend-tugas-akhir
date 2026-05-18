from pydantic import BaseModel, ConfigDict
from datetime import date, datetime
from typing import Optional

class PenjualanBase(BaseModel):
    tanggal: date
    kode_produk: str
    nama_produk: str
    jumlah_terjual: float

class PenjualanCreate(PenjualanBase):
    pass

class PenjualanResponse(PenjualanBase):
    id: int
    uploaded_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

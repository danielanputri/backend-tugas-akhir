from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class ModelRegistryBase(BaseModel):
    kode_produk: str
    file_path: str
    version: Optional[int] = 1
    rmse: Optional[float] = None
    mape: Optional[float] = None

class ModelRegistryCreate(ModelRegistryBase):
    pass

class ModelRegistryResponse(ModelRegistryBase):
    id: int
    trained_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

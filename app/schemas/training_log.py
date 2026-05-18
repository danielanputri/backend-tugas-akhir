from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class TrainingLogBase(BaseModel):
    kode_produk: str
    status: str
    mape_before: Optional[float] = None
    mape_after: Optional[float] = None

class TrainingLogCreate(TrainingLogBase):
    pass

class TrainingLogResponse(TrainingLogBase):
    id: int
    trained_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

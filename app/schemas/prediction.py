from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime

class HealthResponse(BaseModel):
    success: bool
    message: str
    timestamp: datetime

class PredictionRequest(BaseModel):
    model_id: str
    steps: int = Field(default=12, ge=1, le=120)
    confidence_level: float = Field(default=0.95, gt=0, lt=1)

class ConfidenceInterval(BaseModel):
    lower: List[int]
    upper: List[int]

class PredictionData(BaseModel):
    model_id: str
    order: Dict[str, int]
    steps: int
    confidence_level: float
    forecast: List[int]
    confidence_interval: ConfidenceInterval
    inverse_transformed: bool

class PredictionResponse(BaseModel):
    success: bool
    message: str
    data: PredictionData

class ModelEntry(BaseModel):
    id: str
    product_code: str
    data_source: str
    order: Dict[str, int]
    rmse: float
    training_date: str
    n_observations: int

class ModelsListResponse(BaseModel):
    success: bool
    data: Dict[str, Any]

class TrainRequest(BaseModel):
    product_code: str
    data_source: Optional[str] = "latest"
    force_retrain: bool = False
    model_id: Optional[str] = None

class TrainAllRequest(BaseModel):
    data_source: Optional[str] = "latest"
    force_retrain: bool = False
    max_workers: int = Field(default=4, ge=1, le=8)

class JobStatusResponse(BaseModel):
    success: bool
    data: Dict[str, Any]

class PredictionResultBase(BaseModel):
    kode_produk: str
    tanggal_prediksi: datetime
    nilai_prediksi: Optional[float] = None
    confidence_lower: Optional[float] = None
    confidence_upper: Optional[float] = None

class PredictionResultCreate(PredictionResultBase):
    pass

class PredictionResultResponse(PredictionResultBase):
    id: int
    created_at: datetime
    
    model_config = {"from_attributes": True}

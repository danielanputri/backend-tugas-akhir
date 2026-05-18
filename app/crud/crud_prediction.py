from typing import List
from sqlalchemy.orm import Session
from app.crud.base import CRUDBase
from app.models.prediction import PredictionResult
from app.schemas.prediction import PredictionResultCreate

class CRUDPredictionResult(CRUDBase[PredictionResult, PredictionResultCreate, PredictionResultCreate]):
    def get_by_kode_produk(self, db: Session, *, kode_produk: str, skip: int = 0, limit: int = 100) -> List[PredictionResult]:
        return db.query(self.model)\
                 .filter(self.model.kode_produk == kode_produk)\
                 .order_by(self.model.tanggal_prediksi.desc())\
                 .offset(skip).limit(limit).all()

prediction_result = CRUDPredictionResult(PredictionResult)

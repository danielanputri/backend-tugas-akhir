from sqlalchemy import Column, Integer, String, Date, Numeric, DateTime
from sqlalchemy.sql import func
from app.db.base import Base

class PredictionResult(Base):
    __tablename__ = "hasil_prediksi"

    id = Column(Integer, primary_key=True, index=True)
    kode_produk = Column(String(50), nullable=False, index=True)
    tanggal_prediksi = Column(Date, nullable=False, index=True)
    nilai_prediksi = Column(Numeric(10, 2))
    confidence_lower = Column(Numeric(10, 2))
    confidence_upper = Column(Numeric(10, 2))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

from sqlalchemy import Column, Integer, String, Numeric, DateTime
from sqlalchemy.sql import func
from app.db.base import Base

class ModelRegistry(Base):
    __tablename__ = "models"

    id = Column(Integer, primary_key=True, index=True)
    kode_produk = Column(String(50), nullable=False, index=True)
    file_path = Column(String(255))
    version = Column(Integer, default=1)
    mae = Column(Numeric(10, 4))
    rmse = Column(Numeric(10, 4))
    mape = Column(Numeric(10, 4))
    trained_at = Column(DateTime(timezone=True), server_default=func.now())
    arima_p = Column(Integer, nullable=True)
    arima_d = Column(Integer, nullable=True)
    arima_q = Column(Integer, nullable=True)
    prediction_count = Column(Integer, default=0, nullable=False)  # Reset to 0 after each retrain
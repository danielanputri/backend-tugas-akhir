from sqlalchemy import Column, Integer, String, Numeric, DateTime
from sqlalchemy.sql import func
from app.db.base import Base

class TrainingLog(Base):
    __tablename__ = "training_logs"

    id = Column(Integer, primary_key=True, index=True)
    kode_produk = Column(String(50), nullable=False, index=True)
    status = Column(String(20)) # 'success', 'failed'
    mape_before = Column(Numeric(10, 4))
    mape_after = Column(Numeric(10, 4))
    trained_at = Column(DateTime(timezone=True), server_default=func.now())

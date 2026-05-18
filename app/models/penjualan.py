from sqlalchemy import Column, Integer, String, Date, Numeric, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from app.db.base import Base

class Penjualan(Base):
    __tablename__ = "penjualan"

    id = Column(Integer, primary_key=True, index=True)
    tanggal = Column(Date, nullable=False, index=True)
    kode_produk = Column(String(50), nullable=False, index=True)
    nama_produk = Column(String(255), nullable=False)
    nama_supplier = Column(String(255), nullable=True)
    jumlah_terjual = Column(Numeric(10, 2), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('tanggal', 'kode_produk', name='uix_tanggal_kode_produk'),
    )

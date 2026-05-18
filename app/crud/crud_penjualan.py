from typing import List
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from app.crud.base import CRUDBase
from app.models.penjualan import Penjualan
from app.schemas.penjualan import PenjualanCreate

class CRUDPenjualan(CRUDBase[Penjualan, PenjualanCreate, PenjualanCreate]):
    def get_by_kode_produk(self, db: Session, *, kode_produk: str, skip: int = 0, limit: int = 100) -> List[Penjualan]:
        return db.query(self.model)\
                 .filter(self.model.kode_produk == kode_produk)\
                 .order_by(self.model.tanggal.asc())\
                 .offset(skip).limit(limit).all()

    def bulk_insert(self, db: Session, *, objects: List[dict]) -> int:
        if not objects:
            return 0

        stmt = insert(self.model).values(objects)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=['tanggal', 'kode_produk']
        )
        result = db.execute(stmt)
        db.commit()

        if result.rowcount is None or result.rowcount < 0:
            return len(objects)

        return result.rowcount

penjualan = CRUDPenjualan(Penjualan)
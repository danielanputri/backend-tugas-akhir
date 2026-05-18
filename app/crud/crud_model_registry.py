from typing import Optional
from sqlalchemy.orm import Session
from app.crud.base import CRUDBase
from app.models.model_registry import ModelRegistry
from app.schemas.model_registry import ModelRegistryCreate

class CRUDModelRegistry(CRUDBase[ModelRegistry, ModelRegistryCreate, ModelRegistryCreate]):
    def get_latest_by_kode_produk(self, db: Session, *, kode_produk: str) -> Optional[ModelRegistry]:
        return db.query(self.model)\
                 .filter(self.model.kode_produk == kode_produk)\
                 .order_by(self.model.version.desc())\
                 .first()

model_registry = CRUDModelRegistry(ModelRegistry)

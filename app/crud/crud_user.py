from typing import Optional
from sqlalchemy.orm import Session
from app.crud.base import CRUDBase
from app.models.user import User
from app.schemas.user import UserCreate
from app.core.security import get_password_hash

class CRUDUser(CRUDBase[User, UserCreate, UserCreate]):
    def get_by_username(self, db: Session, *, username: str) -> Optional[User]:
        return db.query(self.model).filter(self.model.username == username).first()

    def create(self, db: Session, *, obj_in: UserCreate) -> User:
        db_obj = User(
            username=obj_in.username,
            password_hash=get_password_hash(obj_in.password),
            role=obj_in.role
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

user = CRUDUser(User)

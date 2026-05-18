from datetime import timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.crud.crud_user import user as crud_user
from app.schemas.user import UserCreate, UserResponse
from app.schemas.token import Token
from app.api.dependencies import get_current_user
from app.core import security
from app.core.config import settings
from app.db.database import get_db
from app.models.user import User

router = APIRouter()


@router.post("/register", response_model=UserResponse)
def register(
    *,
    db: Session = Depends(get_db),
    user_in: UserCreate,
) -> Any:
    user = crud_user.get_by_username(db, username=user_in.username)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this username already exists in the system.",
        )
    user = crud_user.create(db, obj_in=user_in)
    return user


@router.post("/login", response_model=Token)
def login_access_token(
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    user = crud_user.get_by_username(db, username=form_data.username)
    if not user or not security.verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Username atau password salah")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        user.id,
        expires_delta=access_token_expires,
        extra_data={"role": user.role},
    )

    # FIX BUG-04: Sertakan role di response
    # Frontend dapat langsung set role tanpa extra roundtrip GET /me
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
    }


@router.get("/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)) -> Any:
    return current_user


@router.post("/logout")
def logout(current_user: User = Depends(get_current_user)) -> Any:
    """
    Logout endpoint.
    JWT bersifat stateless — token tidak dapat di-blacklist secara server-side
    tanpa penyimpanan tambahan. Klien bertanggung jawab menghapus token lokal.
    Endpoint ini memvalidasi token masih valid sebelum memberi respons logout.
    """
    return {
        "success": True,
        "message": "Logout berhasil",
    }
from pydantic import BaseModel
from typing import Optional


class Token(BaseModel):
    access_token: str
    token_type: str
    # FIX BUG-04: Sertakan role langsung di response login
    # Sehingga frontend tidak perlu extra roundtrip GET /me hanya untuk mendapat role
    role: Optional[str] = None


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    role: Optional[str] = None
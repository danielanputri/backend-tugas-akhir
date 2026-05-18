from typing import Any, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.dependencies import get_current_user, require_admin
from app.db.database import get_db
from app.models.user import User

router = APIRouter()


@router.get("")
def list_products(
    search: Optional[str] = Query(default=None, description="Cari berdasarkan nama/kode produk"),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Any:
    """
    Daftar produk unik dari tabel penjualan.
    Berguna untuk dropdown selection di prediction form.
    """
    from app.models.penjualan import Penjualan
    from app.models.model_registry import ModelRegistry

    agg_subq = (
        db.query(
            Penjualan.kode_produk,
            func.max(Penjualan.nama_produk).label("nama_produk"),
            func.count(Penjualan.id).label("jumlah_data"),
            func.max(Penjualan.tanggal).label("last_data"),
        )
        .group_by(Penjualan.kode_produk)
    )

    if search:
        like_q = f"%{search}%"
        agg_subq = agg_subq.filter(
            Penjualan.nama_produk.ilike(like_q) | Penjualan.kode_produk.ilike(like_q)
        )

    agg_subq = agg_subq.limit(limit).all()

    trained_codes = {
        r[0]
        for r in db.query(ModelRegistry.kode_produk).distinct().all()
    }

    data = [
        {
            "kode_produk": row.kode_produk,
            "nama_produk": row.nama_produk,
            "jumlah_data": row.jumlah_data,
            "has_model": row.kode_produk in trained_codes,
            "last_data": str(row.last_data) if row.last_data else None,
        }
        for row in agg_subq
    ]

    return {
        "success": True,
        "total": len(data),
        "data": data,
    }
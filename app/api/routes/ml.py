from typing import Any, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_admin, require_manager
from app.db.database import get_db
from app.models.user import User
from app.services.ml_service import ml_service

router = APIRouter()

PREDICTION_LIMIT = 3  # Maks prediksi sebelum harus retrain


class TrainRequest(BaseModel):
    kode_produk: str
    steps_eval: int = Field(default=3, ge=1, le=12, description="Jumlah bulan untuk evaluasi")


class PredictRequest(BaseModel):
    steps: int = Field(default=1, ge=1, le=1, description="Jumlah bulan ke depan yang diprediksi (dibatasi 1 bulan)")
    confidence_level: float = Field(default=0.95, gt=0, lt=1)


class BulkPredictRequest(BaseModel):
    kode_produk_list: list = Field(..., description="List kode produk yang akan diprediksi")
    steps: int = Field(default=1, ge=1, le=1, description="Jumlah bulan ke depan (dibatasi 1 bulan)")
    confidence_level: float = Field(default=0.95, gt=0, lt=1)


# ─── Train Single (Admin Only) ────────────────────────────────────────────────

@router.post("/train")
def train_single_product(
    request: TrainRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Any:
    """
    Latih model ARIMA untuk satu produk berdasarkan data historis di database.
    Hanya bisa diakses oleh admin. Setelah training berhasil, prediction_count direset ke 0.
    """
    try:
        result = ml_service.train_for_product(
            db, kode_produk=request.kode_produk, steps_eval=request.steps_eval
        )
        # Reset prediction_count setelah retrain sukses
        _reset_prediction_count(db, kode_produk=request.kode_produk)
        return {"success": True, "message": "Model berhasil dilatih.", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


def _reset_prediction_count(db: Session, kode_produk: Optional[str] = None):
    """Reset prediction_count ke 0 setelah model dilatih ulang."""
    from app.models.model_registry import ModelRegistry
    from sqlalchemy import func

    query = db.query(ModelRegistry)
    if kode_produk:
        # Ambil versi terbaru saja
        subq = (
            db.query(func.max(ModelRegistry.id))
            .filter(ModelRegistry.kode_produk == kode_produk)
            .scalar_subquery()
        )
        query = query.filter(ModelRegistry.id == subq)
    
    query.update({"prediction_count": 0}, synchronize_session=False)
    db.commit()


def _run_train_all(db: Session):
    """Helper untuk menjalankan train_all di background."""
    from app.db.database import SessionLocal
    db = SessionLocal()
    try:
        ml_service.train_all(db)
        # Reset semua prediction_count setelah train_all
        _reset_prediction_count(db, kode_produk=None)
    finally:
        db.close()


# ─── Train All (Admin Only) ───────────────────────────────────────────────────

@router.post("/train-all")
def train_all_products(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
) -> Any:
    """
    Trigger batch training untuk semua produk unik di database (berjalan di background).
    Hanya bisa diakses oleh admin.
    """
    background_tasks.add_task(_run_train_all, None)
    return {
        "success": True,
        "message": "Batch training dimulai di background. Hasilnya bisa dicek di tabel training_logs.",
    }


# ─── Train All Sync (Admin Only) ─────────────────────────────────────────────

@router.post("/train-all-sync")
def train_all_products_sync(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Any:
    """
    Jalankan batch training untuk semua produk secara sinkronus.
    Cocok digunakan dari UI untuk mendapatkan hasil langsung.
    """
    try:
        results = ml_service.train_all(db)
        _reset_prediction_count(db, kode_produk=None)
        return {
            "success": True,
            "message": f"Training selesai: {len(results['success'])} berhasil, {len(results['failed'])} gagal.",
            "data": results,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training gagal: {str(e)}")


# ─── Retrain All (foreground, returns metrics) ───────────────────────────────

@router.post("/retrain-all")
def retrain_all_products(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Any:
    """
    Latih ulang semua model menggunakan seluruh data penjualan yang sudah ada di DB.
    Tidak memerlukan upload file — cukup klik dari frontend.
    Berjalan secara foreground dan mengembalikan metrik hasil training.
    Hanya bisa diakses oleh admin.
    """
    try:
        result = ml_service.retrain_all(db)
        # Reset prediction_count untuk semua model setelah retrain
        _reset_prediction_count(db, kode_produk=None)
        return {
            "success": True,
            "message": (
                f"Retrain selesai: {result['success_count']} produk berhasil, "
                f"{result['failed_count']} produk gagal."
            ),
            "data": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Retrain gagal: {str(e)}")


# ─── List Models ──────────────────────────────────────────────────────────────

@router.get("/models")
def list_trained_models(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
) -> Any:
    """
    Tampilkan semua model yang sudah terlatih dari tabel models (versi terbaru per produk).
    """
    from app.models.model_registry import ModelRegistry
    from sqlalchemy import func

    subq = (
        db.query(
            ModelRegistry.kode_produk,
            func.max(ModelRegistry.version).label("max_version"),
        )
        .group_by(ModelRegistry.kode_produk)
        .subquery()
    )
    records = (
        db.query(ModelRegistry)
        .join(
            subq,
            (ModelRegistry.kode_produk == subq.c.kode_produk)
            & (ModelRegistry.version == subq.c.max_version),
        )
        .all()
    )

    return {
        "success": True,
        "total": len(records),
        "data": [
            {
                "kode_produk": r.kode_produk,
                "version": r.version,
                "rmse": float(r.rmse) if r.rmse else None,
                "mape": float(r.mape) if r.mape else None,
                "trained_at": r.trained_at.isoformat() if r.trained_at else None,
                "prediction_count": r.prediction_count if r.prediction_count is not None else 0,
                "is_limit_reached": (r.prediction_count or 0) >= PREDICTION_LIMIT,
                "order": (
                    {"p": r.arima_p, "d": r.arima_d, "q": r.arima_q}
                    if r.arima_p is not None and r.arima_d is not None and r.arima_q is not None
                    else None
                ),
            }
            for r in records
        ],
    }


# ─── Prediction Limit Status ──────────────────────────────────────────────────

@router.get("/prediction-limit")
def get_prediction_limit(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Any:
    """
    Cek status prediction_count untuk semua model.
    Frontend menggunakan ini untuk menentukan apakah tombol prediksi harus di-disable.
    """
    from app.models.model_registry import ModelRegistry
    from sqlalchemy import func

    subq = (
        db.query(
            ModelRegistry.kode_produk,
            func.max(ModelRegistry.version).label("max_version"),
        )
        .group_by(ModelRegistry.kode_produk)
        .subquery()
    )
    records = (
        db.query(ModelRegistry)
        .join(
            subq,
            (ModelRegistry.kode_produk == subq.c.kode_produk)
            & (ModelRegistry.version == subq.c.max_version),
        )
        .all()
    )

    if not records:
        return {
            "success": True,
            "prediction_limit": PREDICTION_LIMIT,
            "global_prediction_count": 0,
            "is_limit_reached": False,
            "data": [],
        }

    # Global limit: tercapai jika SEMUA produk sudah melebihi limit
    global_count = max((r.prediction_count or 0) for r in records)
    is_global_limit = global_count >= PREDICTION_LIMIT

    return {
        "success": True,
        "prediction_limit": PREDICTION_LIMIT,
        "global_prediction_count": global_count,
        "is_limit_reached": is_global_limit,
        "data": [
            {
                "kode_produk": r.kode_produk,
                "prediction_count": r.prediction_count or 0,
                "is_limit_reached": (r.prediction_count or 0) >= PREDICTION_LIMIT,
            }
            for r in records
        ],
    }


# ─── Predict Single ───────────────────────────────────────────────────────────

@router.get("/predict/{kode_produk}")
def predict_product(
    kode_produk: str,
    steps: int = 1,
    confidence_level: float = 0.95,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Any:
    """
    Generate prediksi penjualan untuk kode_produk tertentu menggunakan model terbaru.
    """
    if steps != 1:
        raise HTTPException(status_code=400, detail="steps harus bernilai 1 (prediksi dibatasi 1 bulan ke depan).")
    if not (0 < confidence_level < 1):
        raise HTTPException(status_code=400, detail="confidence_level harus antara 0 dan 1.")

    try:
        result = ml_service.predict_for_product(
            db,
            kode_produk=kode_produk,
            steps=steps,
            confidence_level=confidence_level,
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal melakukan prediksi: {str(e)}")


# ─── Prediction History ───────────────────────────────────────────────────────

@router.get("/history")
def prediction_history(
    kode_produk: Optional[str] = Query(default=None, description="Filter berdasarkan kode produk"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Tampilkan riwayat prediksi yang tersimpan di tabel hasil_prediksi.
    """
    from app.models.prediction import PredictionResult

    query = db.query(PredictionResult)
    if kode_produk:
        query = query.filter(PredictionResult.kode_produk == kode_produk)

    rows = query.order_by(PredictionResult.created_at.desc()).limit(limit).all()

    return {
        "success": True,
        "total": len(rows),
        "data": [
            {
                "id": r.id,
                "kode_produk": r.kode_produk,
                "tanggal_prediksi": str(r.tanggal_prediksi),
                "nilai_prediksi": float(r.nilai_prediksi) if r.nilai_prediksi else None,
                "confidence_lower": float(r.confidence_lower) if r.confidence_lower else None,
                "confidence_upper": float(r.confidence_upper) if r.confidence_upper else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


# ─── Predict Bulk ─────────────────────────────────────────────────────────────

@router.post("/predict-bulk")
def predict_bulk(
    request: BulkPredictRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Any:
    """
    Prediksi untuk multiple produk sekaligus.
    - Cek prediction_count. Jika >= PREDICTION_LIMIT → tolak dengan HTTP 429.
    - Setelah prediksi sukses → increment prediction_count.
    """
    from app.models.model_registry import ModelRegistry
    from sqlalchemy import func

    if not request.kode_produk_list:
        raise HTTPException(status_code=400, detail="kode_produk_list tidak boleh kosong.")

    # ── Cek global limit sebelum proses ──────────────────────────────────────
    subq = (
        db.query(
            ModelRegistry.kode_produk,
            func.max(ModelRegistry.version).label("max_version"),
        )
        .group_by(ModelRegistry.kode_produk)
        .subquery()
    )
    latest_models = (
        db.query(ModelRegistry)
        .join(
            subq,
            (ModelRegistry.kode_produk == subq.c.kode_produk)
            & (ModelRegistry.version == subq.c.max_version),
        )
        .filter(ModelRegistry.kode_produk.in_(request.kode_produk_list))
        .all()
    )

    # Jika semua model sudah mencapai limit, tolak request
    all_over_limit = latest_models and all(
        (m.prediction_count or 0) >= PREDICTION_LIMIT for m in latest_models
    )
    if all_over_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Batas maksimal {PREDICTION_LIMIT} kali prediksi tercapai. "
                "Silakan latih ulang model terlebih dahulu."
            ),
        )

    results = []
    for kode in request.kode_produk_list:
        try:
            pred = ml_service.predict_for_product(
                db,
                kode_produk=str(kode),
                steps=request.steps,
                confidence_level=request.confidence_level,
            )
            results.append(
                {
                    "kode_produk": kode,
                    "predictions": pred["predictions"],
                    "error": None,
                }
            )
        except (ValueError, FileNotFoundError) as e:
            results.append(
                {
                    "kode_produk": kode,
                    "predictions": None,
                    "error": str(e),
                }
            )
        except Exception as e:
            results.append(
                {
                    "kode_produk": kode,
                    "predictions": None,
                    "error": f"Prediksi gagal: {str(e)}",
                }
            )

    # ── Increment prediction_count untuk semua produk yang berhasil ───────────
    success_codes = [r["kode_produk"] for r in results if r["error"] is None]
    if success_codes:
        # Update versi terbaru saja per produk yang berhasil
        for model in latest_models:
            if model.kode_produk in success_codes:
                model.prediction_count = (model.prediction_count or 0) + 1
        db.commit()

    # Hitung max count setelah update
    max_count_after = max(
        ((m.prediction_count or 0) for m in latest_models), default=0
    )

    return {
        "success": True,
        "prediction_count": max_count_after,
        "is_limit_reached": max_count_after >= PREDICTION_LIMIT,
        "data": results,
    }
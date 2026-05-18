from typing import Any, List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.services.ml_service import ml_service

router = APIRouter()


@router.get("/summary")
def dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Summary card untuk dashboard:
    - Total produk yang dipantau
    - Total model yang sudah dilatih
    - Rata-rata akurasi (MAPE) semua model
    - Total record data penjualan
    """
    from app.models.penjualan import Penjualan
    from app.models.model_registry import ModelRegistry
    from sqlalchemy import func

    total_produk = db.query(func.count(Penjualan.kode_produk.distinct())).scalar()
    total_data = db.query(func.count(Penjualan.id)).scalar()

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
        .all()
    )

    total_model_terlatih = len(latest_models)
    avg_mape = None
    if total_model_terlatih > 0:
        mape_values = [float(m.mape) for m in latest_models if m.mape is not None]
        if mape_values:
            avg_mape = round(sum(mape_values) / len(mape_values), 2)

    avg_akurasi = round(100 - avg_mape, 2) if avg_mape is not None else None

    return {
        "success": True,
        "data": {
            "total_produk": total_produk,
            "total_data_penjualan": total_data,
            "total_model_terlatih": total_model_terlatih,
            "avg_mape_persen": avg_mape,
            "avg_akurasi_persen": avg_akurasi,
        },
    }


@router.get("/chart")
def dashboard_chart(
    kode_produk: str = Query(..., description="Kode produk yang ingin ditampilkan"),
    bulan_historis: int = Query(default=12, ge=3, le=60),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Data untuk chart Next.js:
    - Data historis penjualan N bulan terakhir, diagregasi per bulan (SUM jumlah_terjual).
    - Data prediksi yang tersimpan, hanya untuk tanggal SETELAH data historis terakhir,
      dan hanya prediksi terbaru per bulan (berdasarkan created_at).
    """
    from app.models.penjualan import Penjualan
    from app.models.prediction import PredictionResult
    from datetime import date
    from dateutil.relativedelta import relativedelta

    cutoff_date = date.today() - relativedelta(months=bulan_historis)

    # FIX BUG-2: Agregasi SUM per bulan di level DB (PostgreSQL: DATE_TRUNC('month', tanggal)).
    # Ini menangani kasus satu produk dari beberapa supplier di bulan yang sama.
    # DATE_TRUNC mengembalikan timestamp/date awal bulan (misal 2025-03-01),
    # sehingga GROUP BY per bulan bekerja benar tanpa strftime (SQLite-only).
    historis_agg = (
        db.query(
            func.min(Penjualan.tanggal).label("tanggal"),          # tanggal pertama bulan itu
            func.sum(Penjualan.jumlah_terjual).label("jumlah_terjual"),
            func.max(Penjualan.nama_produk).label("nama_produk"),
        )
        .filter(
            Penjualan.kode_produk == kode_produk,
            Penjualan.tanggal >= cutoff_date,
        )
        .group_by(
            func.date_trunc("month", Penjualan.tanggal)
        )
        .order_by(func.min(Penjualan.tanggal).asc())
        .all()
    )

    if not historis_agg:
        raise HTTPException(
            status_code=404,
            detail=f"Tidak ada data historis untuk kode_produk='{kode_produk}'.",
        )

    historis = [
        {
            "tanggal": str(r.tanggal),
            "jumlah_terjual": float(r.jumlah_terjual),
        }
        for r in historis_agg
    ]

    # Tanggal historis terakhir sebagai batas pemisah antara aktual dan prediksi
    last_historis_date = historis_agg[-1].tanggal
    nama_produk = historis_agg[-1].nama_produk or kode_produk

    # FIX BUG-4 & BUG-6: Hanya ambil prediksi SETELAH tanggal historis terakhir.
    # Ini memastikan garis prediksi tidak overlap dengan garis aktual,
    # dan prediksi lama yang sudah menjadi data aktual tidak ikut tampil.
    #
    # FIX BUG-5: Untuk bulan prediksi yang sama (diprediksi ulang),
    # ambil HANYA yang terbaru berdasarkan created_at menggunakan subquery.
    latest_pred_subq = (
        db.query(
            PredictionResult.tanggal_prediksi,
            func.max(PredictionResult.created_at).label("latest_created"),
        )
        .filter(
            PredictionResult.kode_produk == kode_produk,
            PredictionResult.tanggal_prediksi > last_historis_date,
        )
        .group_by(PredictionResult.tanggal_prediksi)
        .subquery()
    )

    prediksi_rows = (
        db.query(PredictionResult)
        .join(
            latest_pred_subq,
            (PredictionResult.tanggal_prediksi == latest_pred_subq.c.tanggal_prediksi)
            & (PredictionResult.created_at == latest_pred_subq.c.latest_created),
        )
        .filter(PredictionResult.kode_produk == kode_produk)
        .order_by(PredictionResult.tanggal_prediksi.asc())
        .all()
    )

    prediksi = [
        {
            "tanggal": str(r.tanggal_prediksi),
            "nilai_prediksi": float(r.nilai_prediksi) if r.nilai_prediksi else None,
            "confidence_lower": float(r.confidence_lower) if r.confidence_lower else None,
            "confidence_upper": float(r.confidence_upper) if r.confidence_upper else None,
        }
        for r in prediksi_rows
    ]

    return {
        "success": True,
        "data": {
            "kode_produk": kode_produk,
            "nama_produk": nama_produk,
            "historis": historis,
            "prediksi": prediksi,
        },
    }

def _urgency_order(status: str) -> int:
    """Beri bobot angka untuk sorting berdasarkan urgency."""
    return {"critical": 0, "warning": 1, "safe": 2}.get(status, 3)


@router.get("/suppliers")
def get_suppliers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Mengambil list nama supplier unik dari data penjualan.
    """
    from app.models.penjualan import Penjualan
    
    suppliers = (
        db.query(Penjualan.nama_supplier)
        .filter(Penjualan.nama_supplier.isnot(None))
        .distinct()
        .order_by(Penjualan.nama_supplier)
        .all()
    )
    
    return {
        "success": True,
        "data": [s[0] for s in suppliers if s[0]]
    }

@router.get("/stock-status")
def stock_status(
    limit: int = Query(default=10, ge=1, le=100),
    page: int = Query(default=1, ge=1),
    sort_by: str = Query(default="urgency", pattern="^(urgency|qty|nama)$"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    search: Optional[str] = Query(default=None),
    supplier: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Daftar produk dengan status urgensi stok.
    - critical : qty_terkini < 50% prediksi
    - warning  : 50% <= qty_terkini < 80% prediksi
    - safe     : qty_terkini >= 80% prediksi
    """
    from app.models.penjualan import Penjualan
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
    trained_models = (
        db.query(ModelRegistry)
        .join(
            subq,
            (ModelRegistry.kode_produk == subq.c.kode_produk)
            & (ModelRegistry.version == subq.c.max_version),
        )
        .all()
    )

    if not trained_models:
        return {"success": True, "total": 0, "page": page, "page_size": limit, "data": []}

    latest_date_subq = (
        db.query(
            Penjualan.kode_produk,
            func.max(Penjualan.tanggal).label("max_tanggal"),
        )
        .group_by(Penjualan.kode_produk)
        .subquery()
    )
    latest_penjualan_query = (
        db.query(Penjualan)
        .join(
            latest_date_subq,
            (Penjualan.kode_produk == latest_date_subq.c.kode_produk)
            & (Penjualan.tanggal == latest_date_subq.c.max_tanggal),
        )
    )
    
    if supplier and supplier.lower() != "all":
        latest_penjualan_query = latest_penjualan_query.filter(Penjualan.nama_supplier.ilike(f"%{supplier}%"))
        
    def normalize_kode(k: str) -> str:
        k_str = str(k).strip()
        if k_str.endswith(".0"):
            return k_str[:-2]
        return k_str

    latest_penjualan = latest_penjualan_query.all()
    latest_map = {normalize_kode(row.kode_produk): row for row in latest_penjualan}

    items = []
    for model_rec in trained_models:
        kode = normalize_kode(model_rec.kode_produk)
        
        # If supplier filter is active but this product isn't from this supplier, skip
        if supplier and supplier.lower() != "all" and kode not in latest_map:
            continue
            
        latest_row = latest_map.get(kode)
        qty_terkini = float(latest_row.jumlah_terjual) if latest_row else 0.0
        nama_produk = latest_row.nama_produk if latest_row else kode
        last_updated = (
            latest_row.uploaded_at.isoformat() if latest_row and latest_row.uploaded_at else None
        )
        nama_sup = latest_row.nama_supplier if latest_row else None
        
        # Apply search filter
        if search:
            search_lower = search.lower()
            if search_lower not in kode.lower() and search_lower not in nama_produk.lower():
                continue

        try:
            pred_result = ml_service.predict_for_product_raw(db, kode, steps=1)
            pred_entry = pred_result["predictions"][0]
            qty_prediksi = float(pred_entry["nilai_prediksi"])
            # Ambil tanggal prediksi untuk label header kolom
            tanggal_prediksi_str = str(pred_entry.get("tanggal", ""))
        except Exception:
            continue

        selisih = qty_terkini - qty_prediksi
        if qty_prediksi > 0:
            pct = round((selisih / qty_prediksi) * 100, 2)
            ratio = qty_terkini / qty_prediksi
        else:
            pct = 0.0
            ratio = 1.0

        if ratio < 0.5:
            status = "critical"
            deficit = abs(selisih)
            rekomendasi = f"Segera tambah stok minimal {int(deficit)} unit"
        elif ratio < 0.8:
            status = "warning"
            deficit = abs(selisih)
            rekomendasi = f"Pertimbangkan penambahan stok sekitar {int(deficit)} unit"
        else:
            status = "safe"
            rekomendasi = "Stok aman"

        # Label bulan stok saat ini (dari data xlsx yang diupload)
        stok_bulan_label = None
        if latest_row and latest_row.tanggal:
            tgl = latest_row.tanggal
            BULAN_ID = ["Jan","Feb","Mar","Apr","Mei","Jun","Jul","Agu","Sep","Okt","Nov","Des"]
            stok_bulan_label = f"{BULAN_ID[tgl.month - 1]} {tgl.year}"

        # Label bulan prediksi
        prediksi_bulan_label = None
        if tanggal_prediksi_str:
            try:
                from dateutil.parser import parse as parse_date
                tgl_pred = parse_date(tanggal_prediksi_str).date()
                BULAN_ID = ["Jan","Feb","Mar","Apr","Mei","Jun","Jul","Agu","Sep","Okt","Nov","Des"]
                prediksi_bulan_label = f"{BULAN_ID[tgl_pred.month - 1]} {tgl_pred.year}"
            except Exception:
                pass

        items.append(
            {
                "kode_produk": kode,
                "nama_produk": nama_produk,
                "qty_terkini": qty_terkini,
                "stok_bulan_label": stok_bulan_label,
                "qty_prediksi_bulan_depan": qty_prediksi,
                "prediksi_bulan_label": prediksi_bulan_label,
                "selisih": round(selisih, 2),
                "persentase_perubahan": pct,
                "status_urgensi": status,
                "rekomendasi": rekomendasi,
                "last_updated": last_updated,
                "nama_supplier": nama_sup,
                "mape": float(model_rec.mape) if model_rec.mape is not None else None,
                "rmse": float(model_rec.rmse) if model_rec.rmse is not None else None,
            }
        )

    reverse = order == "desc"
    if sort_by == "urgency":
        items.sort(key=lambda x: _urgency_order(x["status_urgensi"]), reverse=reverse)
    elif sort_by == "qty":
        items.sort(key=lambda x: x["qty_terkini"], reverse=reverse)
    elif sort_by == "nama":
        items.sort(key=lambda x: x["nama_produk"].lower(), reverse=not reverse)

    total = len(items)
    start = (page - 1) * limit
    end = start + limit
    paginated = items[start:end]

    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": limit,
        "data": paginated,
    }

@router.get("/chart-comparison")
def chart_comparison(
    kode_produk: str = Query(
        ..., description="Kode produk dipisahkan koma, contoh: 8992,8993"
    ),
    bulan_historis: int = Query(default=6, ge=3, le=60),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Data historis + prediksi untuk beberapa produk sekaligus (untuk chart comparison).
    kode_produk: comma-separated string, misal '8992003170403,8992003170404'
    """
    from app.models.penjualan import Penjualan
    from app.models.prediction import PredictionResult
    from datetime import date
    from dateutil.relativedelta import relativedelta

    kode_list = [k.strip() for k in kode_produk.split(",") if k.strip()]
    if not kode_list:
        raise HTTPException(status_code=400, detail="Parameter kode_produk tidak boleh kosong.")

    cutoff_date = date.today() - relativedelta(months=bulan_historis)
    result = []

    for kode in kode_list:
        historis_rows = (
            db.query(Penjualan)
            .filter(
                Penjualan.kode_produk == kode,
                Penjualan.tanggal >= cutoff_date,
            )
            .order_by(Penjualan.tanggal.asc())
            .all()
        )

        prediksi_rows = (
            db.query(PredictionResult)
            .filter(PredictionResult.kode_produk == kode)
            .order_by(PredictionResult.tanggal_prediksi.asc())
            .all()
        )

        nama_produk = historis_rows[-1].nama_produk if historis_rows else kode

        result.append(
            {
                "kode_produk": kode,
                "nama_produk": nama_produk,
                "historis": [
                    {
                        "tanggal": str(r.tanggal),
                        "jumlah_terjual": float(r.jumlah_terjual),
                    }
                    for r in historis_rows
                ],
                "prediksi": [
                    {
                        "tanggal": str(r.tanggal_prediksi),
                        "nilai_prediksi": float(r.nilai_prediksi) if r.nilai_prediksi else None,
                        "confidence_lower": float(r.confidence_lower) if r.confidence_lower else None,
                        "confidence_upper": float(r.confidence_upper) if r.confidence_upper else None,
                    }
                    for r in prediksi_rows
                ],
            }
        )

    return {"success": True, "data": result}
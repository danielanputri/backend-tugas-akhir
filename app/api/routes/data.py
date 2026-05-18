import io
import shutil
import pandas as pd
import openpyxl
import re
from datetime import datetime
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_admin
from app.core.config import settings
from app.db.database import get_db
from app.models.user import User
from app import models
from app.crud.crud_penjualan import penjualan as crud_penjualan

router = APIRouter()

# ================= CONSTANT =================
MONTH_LABELS = {
    'january': 1, 'januari': 1, 'jan': 1,
    'february': 2, 'februari': 2, 'feb': 2,
    'march': 3, 'maret': 3, 'mar': 3,
    'april': 4, 'apr': 4,
    'may': 5, 'mei': 5,
    'june': 6, 'juni': 6, 'jun': 6,
    'july': 7, 'juli': 7, 'jul': 7,
    'august': 8, 'agustus': 8, 'aug': 8, 'agu': 8,
    'september': 9, 'sep': 9,
    'october': 10, 'oktober': 10, 'oct': 10, 'okt': 10,
    'november': 11, 'nov': 11,
    'december': 12, 'desember': 12, 'dec': 12, 'des': 12
}

INVALID_TEMPLATE_CODE  = "INVALID_TEMPLATE"
CSV_CONFLICT_CODE      = "CSV_CONFLICT"
CSV_INSUFFICIENT_CODE  = "CSV_INSUFFICIENT_DATA"
MIN_MONTHS             = 18

# ================= UTIL =================
def _template_error(msg: str, t: str):
    raise HTTPException(
        status_code=422,
        detail={"error_code": INVALID_TEMPLATE_CODE, "template_type": t, "message": msg}
    )

def parse_indonesian_date(date_str: str):
    m = re.search(r'(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})', date_str)
    if not m:
        return None
    month = MONTH_LABELS.get(m.group(2).lower())
    if not month:
        return None
    return datetime(int(m.group(3)), month, int(m.group(1))).date()

def clean_kode(val):
    if pd.isna(val):
        return None
    val = str(val).strip()
    if "e+" in val.lower():
        try:
            return str(int(float(val)))
        except Exception:
            return None
    return re.sub(r"\.0$", "", val)

# ================= CSV VALIDATOR =================
def _validate_csv(path):
    try:
        df = pd.read_csv(path)
    except Exception as e:
        _template_error(str(e), "csv")

    df.columns = df.columns.str.strip()

    required = ['Periode', 'Supplier', 'Kode Article', 'Nama Article', 'Qty']
    missing = [c for c in required if c not in df.columns]
    if missing:
        _template_error(f"Kolom tidak lengkap: {missing}", "csv")

    df['Periode'] = pd.to_datetime(df['Periode'], errors='coerce')
    df['Qty'] = pd.to_numeric(df['Qty'], errors='coerce')

    df['Kode Article'] = df['Kode Article'].apply(clean_kode)
    df['Nama Article'] = df['Nama Article'].astype(str).str.strip()

    df = df.dropna(subset=['Periode', 'Kode Article', 'Nama Article', 'Qty'])
    df = df[df['Qty'] > 0]

    if df.empty:
        _template_error("Tidak ada data valid setelah cleaning", "csv")

    # VALIDASI MIN 18 BULAN
    df['_ym'] = df['Periode'].dt.to_period('M')
    counts = df.groupby('Kode Article')['_ym'].nunique()
    invalid = counts[counts < MIN_MONTHS]

    if len(invalid) > 0:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": CSV_INSUFFICIENT_CODE,
                "message": (
                    f"Produk '{invalid.index[0]}' hanya punya {invalid.iloc[0]} bulan data "
                    f"(minimum {MIN_MONTHS} bulan)."
                ),
            },
        )

    df = df.drop(columns=['_ym'])
    return df

# ================= XLSX VALIDATOR =================
def _validate_xlsx(path):
    try:
        df_raw = pd.read_excel(path, header=None, dtype=object)
    except Exception as e:
        _template_error(str(e), "xlsx")

    # 1. WAJIB ADA JUDUL EXACT
    found_title = False
    for i in range(min(5, len(df_raw))):
        row_cells = [str(v).strip().lower() for v in df_raw.iloc[i] if pd.notna(v)]
        if any(cell == "laporan penjualan per supplier" for cell in row_cells):
            found_title = True
            break

    if not found_title:
        _template_error(
            "Format XLSX tidak valid (judul tidak sesuai template)",
            "xlsx"
        )

    # 2. WAJIB ADA SUPPLIER
    found_supplier_meta = False
    for i in range(min(10, len(df_raw))):
        for cell_val in df_raw.iloc[i]:
            if pd.notna(cell_val):
                cell_str = str(cell_val).strip()
                if re.match(r'^supplier\s*:\s*.+', cell_str, re.IGNORECASE):
                    found_supplier_meta = True
                    break
        if not found_supplier_meta:
            cells = [str(v).strip() for v in df_raw.iloc[i] if pd.notna(v)]
            joined = " ".join(cells)
            if re.match(r'^supplier\s*:\s*.+', joined, re.IGNORECASE):
                found_supplier_meta = True
        if found_supplier_meta:
            break

    if not found_supplier_meta:
        _template_error(
            "Format XLSX tidak valid (baris 'Supplier : <nama>' tidak ditemukan)",
            "xlsx"
        )

    # DETEKSI HEADER
    header_idx = None
    for i in range(min(40, len(df_raw))):
        cells = [str(c).lower() for c in df_raw.iloc[i] if pd.notna(c)]
        if (
            any("kode" in c for c in cells) and
            any("nama" in c for c in cells) and
            any(k in c for c in cells for k in ["qty", "jumlah", "quantity"])
        ):
            header_idx = i
            break

    if header_idx is None:
        _template_error(
            "Header tidak ditemukan (Kode, Nama, Qty wajib ada)",
            "xlsx"
        )

    # LOAD DATA
    df = pd.read_excel(path, skiprows=header_idx)
    df.columns = [str(c).lower().strip() for c in df.columns]

    col_map = {}
    for c in df.columns:
        if "kode" in c and "kode" not in col_map.values():
            col_map[c] = "kode"
        elif "nama" in c and "nama" not in col_map.values():
            col_map[c] = "nama"
        elif any(k in c for k in ["qty", "jumlah", "quantity"]) and "qty" not in col_map.values():
            col_map[c] = "qty"

    df = df.rename(columns=col_map)

    if not all(c in df.columns for c in ["kode", "nama", "qty"]):
        _template_error("Kolom tidak valid (Kode, Nama, Qty wajib ada)", "xlsx")

    # EXTRACT META
    supplier = None
    tanggal = None

    for i in range(header_idx):
        row = " ".join(str(v) for v in df_raw.iloc[i] if pd.notna(v))

        if not supplier and "supplier" in row.lower():
            m = re.search(r'Supplier\s*:\s*(.+)', row, re.IGNORECASE)
            if m:
                supplier = m.group(1).strip()

        if not tanggal:
            dates = re.findall(r'(\d{1,2}\s+[a-zA-Z]+\s+\d{4})', row)
            for d in dates:
                parsed = parse_indonesian_date(d)
                if parsed:
                    tanggal = parsed
                    break

    if not supplier:
        _template_error(
            "Nama supplier tidak dapat dibaca dari file (pastikan format: 'Supplier : <nama>')",
            "xlsx"
        )

    if not tanggal:
        tanggal = datetime.now().date()

    # CLEAN DATA
    df['kode'] = df['kode'].apply(clean_kode)
    df['nama'] = df['nama'].astype(str).str.strip()
    df['qty'] = pd.to_numeric(df['qty'], errors='coerce')

    df = df.dropna(subset=['kode', 'nama', 'qty'])
    df = df[df['qty'] > 0]
    df = df[df['kode'].str.match(r'^\d+$', na=False)]

    if df.empty:
        _template_error(
            "Data kosong setelah cleaning — pastikan format benar",
            "xlsx"
        )

    df['Periode'] = tanggal

    return df, tanggal, supplier

# ================= TEMPLATE =================
@router.get("/template/csv")
def template_csv(
    current_user: User = Depends(require_admin),
):
    """Download template CSV data historis (18 bulan contoh data)."""
    SUPPLIER = "P0047 - PT.JAVAS TRIPTA MANDALA"
    PRODUCTS = [
        ("8992003170403", "ANTANGIN 4 S ( 1 PAK ISI 20)"),
        ("8992003783399", "ANTANGIN GINGER MINT 15 ML"),
        ("8992003782354", "ANTANGIN JRG SYRUP 15ML"),
    ]

    import random
    random.seed(42)
    lines = ["Periode,Supplier,Kode Article,Nama Article,Qty"]
    for kode, nama in PRODUCTS:
        for month_offset in range(MIN_MONTHS):
            year = 2023 + month_offset // 12
            m = (month_offset % 12) + 1
            qty = random.randint(5, 50)
            lines.append(f"{year}-{m:02d}-01,{SUPPLIER},{kode},{nama},{qty}")

    content = "\n".join(lines) + "\n"

    return StreamingResponse(
        io.BytesIO(content.encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=template.csv"},
    )


@router.get("/template/xlsx")
def template_xlsx(
    current_user: User = Depends(require_admin),
):
    """Download template XLSX data penjualan bulanan."""
    wb = openpyxl.Workbook()
    ws = wb.active

    ws.append(["Laporan Penjualan Per Supplier"])
    ws.append(["Supplier : P0047 - PT.JAVAS TRIPTA MANDALA"])
    ws.append(["Periode Tanggal : 01 January 2025 s.d. 31 January 2025"])
    ws.append([])
    ws.append(["Kode Article", "Nama Article", "Qty"])
    ws.append(["8992003170403", "ANTANGIN 4 S", 10])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Template_Penjualan_Bulanan.xlsx"},
    )


# ================= UPLOAD =================
@router.post("/upload")
def upload_data(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Any:
    name = file.filename.lower()
    if not name.endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(400, "Format tidak didukung. Gunakan .csv atau .xlsx")

    path = settings.UPLOAD_DIR / file.filename
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    if name.endswith(".csv"):
        df = _validate_csv(path)

        # CEK KONFLIK CSV: produk sudah ada di DB → tolak
        csv_kodes = df['Kode Article'].unique().tolist()
        existing_in_db = (
            db.query(models.Penjualan.kode_produk)
            .filter(models.Penjualan.kode_produk.in_(csv_kodes))
            .distinct()
            .all()
        )
        existing_model = (
            db.query(models.ModelRegistry.kode_produk)
            .filter(models.ModelRegistry.kode_produk.in_(csv_kodes))
            .distinct()
            .all()
        )
        conflict_kodes = {r[0] for r in existing_in_db} | {r[0] for r in existing_model}
        if conflict_kodes:
            products = sorted(conflict_kodes)
            msg = (
                f"Model untuk produk '{products[0]}' sudah ada."
                if len(products) == 1
                else f"Model untuk {len(products)} produk sudah ada: {', '.join(products[:3])}"
                + ("" if len(products) <= 3 else f" dan {len(products)-3} lainnya")
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": CSV_CONFLICT_CODE,
                    "message": msg + " CSV hanya boleh digunakan untuk inisialisasi pertama kali.",
                    "products": products,
                },
            )

        records = [
            {
                "tanggal": row["Periode"].date(),
                "kode_produk": row["Kode Article"],
                "nama_produk": row["Nama Article"],
                "nama_supplier": row["Supplier"],
                "jumlah_terjual": float(row["Qty"]),
            }
            for _, row in df.iterrows()
        ]

    else:
        if name.endswith(".xls"):
            try:
                pd.read_excel(path, engine="xlrd", nrows=1)
            except Exception:
                raise HTTPException(
                    400,
                    "File .xls tidak dapat dibaca. Silakan simpan ulang sebagai .xlsx"
                )

        df, tanggal, supplier = _validate_xlsx(path)

        # CEK DUPLIKAT XLSX: kode_produk + YYYY-MM sudah ada
        uploaded_keys = set()
        for _, row in df.iterrows():
            tgl = row["Periode"]
            if isinstance(tgl, datetime):
                tgl = tgl.date()
            uploaded_keys.add((row["kode"], tgl.strftime("%Y-%m")))

        uploaded_kodes = list({r["kode"] for _, r in df.iterrows()})
        candidates = (
            db.query(
                models.Penjualan.kode_produk,
                models.Penjualan.nama_produk,
                models.Penjualan.tanggal,
            )
            .filter(models.Penjualan.kode_produk.in_(uploaded_kodes))
            .all()
        )

        existing = []
        seen = set()
        for c in candidates:
            c_tgl = c.tanggal
            if isinstance(c_tgl, datetime):
                c_tgl = c_tgl.date()
            key = (c.kode_produk, c_tgl.strftime("%Y-%m"))
            if key in uploaded_keys and key not in seen:
                seen.add(key)
                existing.append({
                    "kode": c.kode_produk,
                    "nama": c.nama_produk,
                    "bulan": c_tgl.strftime("%B %Y"),
                })

        if existing:
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": "CONFLICT",
                    "message": (
                        f"{len(existing)} produk sudah ada di database. "
                        "Hapus data terkait lalu upload ulang."
                    ),
                    "products": existing,
                },
            )

        records = [
            {
                "tanggal": tanggal,
                "kode_produk": row["kode"],
                "nama_produk": row["nama"],
                "nama_supplier": supplier,
                "jumlah_terjual": float(row["qty"]),
            }
            for _, row in df.iterrows()
        ]

    if not records:
        raise HTTPException(400, "Semua baris tidak valid setelah cleaning.")

    inserted = crud_penjualan.bulk_insert(db, objects=records)

    return {
        "success": True,
        "rows": inserted,
        "message": f"{len(records)} data diproses",
    }
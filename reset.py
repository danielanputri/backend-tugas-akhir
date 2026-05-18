"""
Reset script — jalankan sesuai kebutuhan:

  python reset.py --mode model       # hapus model & prediksi saja, data penjualan dipertahankan
  python reset.py --mode full        # hapus semua termasuk data penjualan
  python reset.py --mode pkl-only    # hapus file .pkl saja, DB tidak disentuh
  python reset.py --mode db-only     # hapus tabel model & prediksi saja, tanpa hapus .pkl
"""
import argparse
import shutil
from pathlib import Path

def get_db():
    from app.db.database import SessionLocal
    return SessionLocal()

def delete_pkl_files(models_dir: Path):
    pkl_files = list(models_dir.glob("*.pkl"))
    if not pkl_files:
        print("  Tidak ada file .pkl ditemukan.")
        return
    for f in pkl_files:
        f.unlink()
        print(f"  Hapus: {f.name}")
    print(f"  Total: {len(pkl_files)} file .pkl dihapus.")

def reset_db_models(db):
    from sqlalchemy import text
    db.execute(text("DELETE FROM hasil_prediksi"))
    db.execute(text("DELETE FROM models"))
    db.execute(text("DELETE FROM training_logs"))
    db.commit()
    print("  Tabel models, hasil_prediksi, training_logs → dikosongkan.")

def reset_db_full(db):
    from sqlalchemy import text
    db.execute(text("DELETE FROM hasil_prediksi"))
    db.execute(text("DELETE FROM models"))
    db.execute(text("DELETE FROM training_logs"))
    db.execute(text("DELETE FROM penjualan"))
    db.commit()
    print("  Semua tabel (termasuk penjualan) → dikosongkan.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["model", "full", "pkl-only", "db-only"],
                        required=True)
    args = parser.parse_args()

    from app.core.config import settings
    models_dir = settings.MODELS_DIR

    print(f"\n=== Reset mode: {args.mode} ===")

    if args.mode == "pkl-only":
        print("Menghapus file .pkl...")
        delete_pkl_files(models_dir)

    elif args.mode == "db-only":
        print("Menghapus data model & prediksi dari database...")
        db = get_db()
        try:
            reset_db_models(db)
        finally:
            db.close()

    elif args.mode == "model":
        print("Menghapus file .pkl...")
        delete_pkl_files(models_dir)
        print("Menghapus data model & prediksi dari database...")
        db = get_db()
        try:
            reset_db_models(db)
        finally:
            db.close()

    elif args.mode == "full":
        confirm = input("\n⚠️  Ini akan menghapus SEMUA data termasuk penjualan. Ketik 'ya' untuk lanjut: ")
        if confirm.strip().lower() != "ya":
            print("Dibatalkan.")
            return
        print("Menghapus file .pkl...")
        delete_pkl_files(models_dir)
        print("Menghapus semua data dari database...")
        db = get_db()
        try:
            reset_db_full(db)
        finally:
            db.close()

    print("\n✓ Reset selesai. Silakan retrain model dari awal.\n")

if __name__ == "__main__":
    main()
    
    
    
import os
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME: str = "ARIMA Forecasting API"
    
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent

    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/stock_forecast")

    # SECRET_KEY wajib diset via environment variable di production
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")

    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

    DATA_DIR: Path = BASE_DIR / "data"
    MODELS_DIR: Path = BASE_DIR / "app" / "ml_models"
    UPLOAD_DIR: Path = BASE_DIR / "data" / "uploads"
    
    REGISTRY_FILE: Path = MODELS_DIR / "registry.json"

    MAX_UPLOAD_MB: int = 10
    MAX_FORECAST_STEPS: int = 120

    # Set CORS_ORIGINS via env, pisahkan dengan koma. Contoh:
    # CORS_ORIGINS=http://localhost:3000,https://yourdomain.com
    # Default hanya localhost untuk development.
    _cors_raw: str = os.getenv("CORS_ORIGINS", "http://localhost:3000")

    @property
    def CORS_ORIGINS(self) -> List[str]:
        raw = self._cors_raw.strip()
        # Handle format JSON array: ["http://localhost:3000"]
        if raw.startswith("["):
            import json
            try:
                return json.loads(raw)
            except Exception:
                pass
        # Handle format comma-separated: http://localhost:3000,https://example.com
        return [o.strip() for o in raw.split(",") if o.strip()]
    
    MASS_TRAIN_WORKERS: int = 4

settings = Settings()

# Validasi SECRET_KEY — harus diset dan panjang minimal 32 karakter
if not settings.SECRET_KEY or len(settings.SECRET_KEY) < 32:
    raise RuntimeError(
        "SECRET_KEY belum diset atau terlalu pendek (minimal 32 karakter). "
        "Set environment variable SECRET_KEY sebelum menjalankan aplikasi."
    )

for d in [settings.DATA_DIR, settings.MODELS_DIR, settings.UPLOAD_DIR]:
    d.mkdir(parents=True, exist_ok=True)
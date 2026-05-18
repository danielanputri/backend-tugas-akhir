import os
import json
from pathlib import Path
from typing import List
from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME: str = "ARIMA Forecasting API"

    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent

    MAX_UPLOAD_MB: int = 10
    MAX_FORECAST_STEPS: int = 120
    MASS_TRAIN_WORKERS: int = 4

    def __init__(self):
        self.DATABASE_URL: str = os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:password@localhost:5432/stock_forecast"
        )
        self.SECRET_KEY: str = os.getenv("SECRET_KEY", "")
        self.ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
            os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")
        )

        self.DATA_DIR: Path = self.BASE_DIR / "data"
        self.MODELS_DIR: Path = self.BASE_DIR / "app" / "ml_models"
        self.UPLOAD_DIR: Path = self.BASE_DIR / "data" / "uploads"
        self.REGISTRY_FILE: Path = self.MODELS_DIR / "registry.json"

        # Parse CORS_ORIGINS dari env
        # Format JSON array: ["https://example.com","http://localhost:3000"]
        # Format comma-separated: https://example.com,http://localhost:3000
        cors_raw: str = os.getenv("CORS_ORIGINS", "http://localhost:3000").strip()
        if cors_raw.startswith("["):
            try:
                self.CORS_ORIGINS: List[str] = json.loads(cors_raw)
            except Exception:
                self.CORS_ORIGINS = [o.strip() for o in cors_raw.split(",") if o.strip()]
        else:
            self.CORS_ORIGINS = [o.strip() for o in cors_raw.split(",") if o.strip()]

        import logging
        logging.getLogger("main").info(f"CORS_ORIGINS loaded: {self.CORS_ORIGINS}")

settings = Settings()

# Validasi SECRET_KEY — harus diset dan panjang minimal 32 karakter
if not settings.SECRET_KEY or len(settings.SECRET_KEY) < 32:
    raise RuntimeError(
        "SECRET_KEY belum diset atau terlalu pendek (minimal 32 karakter). "
        "Set environment variable SECRET_KEY sebelum menjalankan aplikasi."
    )

for d in [settings.DATA_DIR, settings.MODELS_DIR, settings.UPLOAD_DIR]:
    d.mkdir(parents=True, exist_ok=True)
import math
import logging
import threading
import joblib
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from dateutil.relativedelta import relativedelta

import warnings
from pmdarima import auto_arima
from scipy.stats import boxcox, shapiro
from scipy.special import inv_boxcox
from sklearn.metrics import mean_squared_error
from sqlalchemy.orm import Session

from app.core.config import settings

warnings.filterwarnings("ignore")
logger = logging.getLogger("arima_service")


# ─── KONSTANTA ────────────────────────────────────────────────────────────────
_LAMBDA_NO_TRANSFORM_LOW  = 0.9
_LAMBDA_NO_TRANSFORM_HIGH = 1.1
_BOXCOX_MIN_MEAN_VOLUME   = 50.0   # rata-rata < 50 unit/bulan → skip Box-Cox


class MLService:
    def __init__(self):
        self._lock = threading.Lock()

    # =========================================================================
    # Helper Box-Cox
    # =========================================================================
    def _detect_and_apply_boxcox(
        self, series: pd.Series
    ) -> Tuple[np.ndarray, Optional[float], float]:
        """
        Deteksi apakah data membutuhkan transformasi Box-Cox, lalu terapkan.

        Guard dipasang SEBELUM boxcox() dipanggil sehingga estimasi lambda
        tidak pernah dijalankan jika mean < _BOXCOX_MIN_MEAN_VOLUME.

        FIX: shift dikembalikan sebagai nilai ketiga (single source of truth).
        train_for_product tidak perlu menghitung shift sendiri lagi.

        Returns:
            (y_transformed, boxcox_lambda, boxcox_shift)

            boxcox_lambda = None  → tidak ada transformasi
            boxcox_shift  = 0.0   → tidak ada shift
        """
        # ── Guard: skip Box-Cox untuk data volume kecil ──────────────────────
        mean_volume = series.mean()
        if mean_volume < _BOXCOX_MIN_MEAN_VOLUME:
            logger.info(
                f"Box-Cox: rata-rata volume={mean_volume:.2f} < {_BOXCOX_MIN_MEAN_VOLUME} "
                f"→ transformasi di-skip (data volume kecil)"
            )
            return series.values.astype(float), None, 0.0

        y = series.values.copy().astype(float)

        # ── Hitung shift jika ada nilai <= 0 (syarat Box-Cox: semua nilai > 0) ─
        min_val = y.min()
        shift   = 0.0
        if min_val <= 0:
            shift = abs(min_val) + 1.0
            y     = y + shift
            logger.debug(f"Box-Cox: applied shift={shift:.4f} to ensure all values > 0")

        try:
            y_transformed, lam = boxcox(y)

            # Lambda ≈ 1.0 → transformasi tidak signifikan, skip
            if _LAMBDA_NO_TRANSFORM_LOW <= lam <= _LAMBDA_NO_TRANSFORM_HIGH:
                logger.info(
                    f"Box-Cox: lambda={lam:.4f} ≈ 1.0 → transformasi tidak diperlukan"
                )
                # Kembalikan shift meskipun tidak transform,
                # agar bundle pkl konsisten
                return series.values.astype(float), None, shift

            logger.info(
                f"Box-Cox: lambda={lam:.4f} diterapkan "
                f"({'log' if abs(lam) < 0.1 else 'sqrt' if 0.4 < lam < 0.6 else 'power'})"
            )
            # Kembalikan 3 nilai: data transform, lambda, shift
            return y_transformed, lam, shift

        except Exception as e:
            logger.warning(f"Box-Cox gagal, lanjut tanpa transformasi: {e}")
            return series.values.astype(float), None, shift

    def _inverse_boxcox(
        self,
        values: np.ndarray,
        lam: Optional[float],
        shift: float = 0.0,
    ) -> np.ndarray:
        """
        Kembalikan nilai dari ruang Box-Cox ke skala asli.
        Jika lam=None (tidak ada transformasi), kembalikan nilai apa adanya.
        """
        if lam is None:
            return np.asarray(values, dtype=float)

        result = inv_boxcox(np.asarray(values, dtype=float), lam)
        if shift > 0:
          result = result - shift
        result = np.where(np.isfinite(result), result, 0.0)  # ← guard nan/inf
        return np.maximum(result, 0.0)

    # =========================================================================
    # Helper lain (tidak berubah)
    # =========================================================================
    def _get_historical_data(self, db: Session, kode_produk: str) -> pd.Series:
        from app.models.penjualan import Penjualan
        rows = (
            db.query(Penjualan)
            .filter(Penjualan.kode_produk == kode_produk)
            .order_by(Penjualan.tanggal.asc())
            .all()
        )
        if not rows:
            raise ValueError(f"No data found in database for kode_produk='{kode_produk}'")
        dates  = [r.tanggal for r in rows]
        values = [float(r.jumlah_terjual) for r in rows]
        return pd.Series(values, index=pd.to_datetime(dates))

    def _get_all_kode_produk(self, db: Session) -> List[str]:
        from app.models.penjualan import Penjualan
        rows = db.query(Penjualan.kode_produk).distinct().all()
        return [r[0] for r in rows]

    def _compute_metrics(
        self, actual: np.ndarray, predicted: np.ndarray
    ) -> Dict[str, float]:
        """Hitung RMSE dan MAPE — selalu dalam skala ASLI (setelah inverse transform)."""
        actual    = np.array(actual,    dtype=float)
        predicted = np.array(predicted, dtype=float)
        rmse      = float(np.sqrt(mean_squared_error(actual, predicted)))
        mask      = actual != 0
        mape      = (
            float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100)
            if mask.sum() > 0 else float("inf")
        )
        return {"rmse": round(rmse, 4), "mape": round(mape, 4)}

    def _load_model_from_db(self, db: Session, kode_produk: str):
        """
        Load bundle {model, boxcox_lambda, boxcox_shift} dari .pkl.
        Backward-compatible dengan model lama (format bukan dict → lambda=None).
        """
        from app.models.model_registry import ModelRegistry
        record = (
            db.query(ModelRegistry)
            .filter(ModelRegistry.kode_produk == kode_produk)
            .order_by(ModelRegistry.version.desc())
            .first()
        )
        if not record:
            raise ValueError(f"No trained model found for kode_produk='{kode_produk}'")

        pkl_path = Path(record.file_path)
        if not pkl_path.exists():
            raise FileNotFoundError(f"Model file not found at: {pkl_path}")

        loaded = joblib.load(pkl_path)

        if isinstance(loaded, dict):
            model         = loaded["model"]
            boxcox_lambda = loaded.get("boxcox_lambda", None)
            boxcox_shift  = loaded.get("boxcox_shift",  0.0)
        else:
            # Model lama (sebelum Box-Cox) — tidak ada transformasi
            model         = loaded
            boxcox_lambda = None
            boxcox_shift  = 0.0

        return model, record, boxcox_lambda, boxcox_shift

    # =========================================================================
    # train_for_product
    # =========================================================================
    def train_for_product(
        self, db: Session, kode_produk: str, steps_eval: int = 3
    ) -> Dict[str, Any]:
        from app.models.model_registry import ModelRegistry
        from app.models.training_log import TrainingLog

        logger.info(f"Training model for kode_produk='{kode_produk}'")

        series = self._get_historical_data(db, kode_produk)
        n      = len(series)
        if n < 18:
            raise ValueError(
                f"Data tidak cukup untuk training ARIMA. "
                f"Minimal 18 data, ditemukan {n}."
            )

        # FIX: terima 3 nilai — shift tidak dihitung ulang di sini
        y_transformed, boxcox_lambda, boxcox_shift = self._detect_and_apply_boxcox(series)

        series_transformed = pd.Series(y_transformed, index=series.index)
        train         = series_transformed.iloc[:-steps_eval] if n > steps_eval else series_transformed
        test          = series_transformed.iloc[-steps_eval:]  if n > steps_eval else series_transformed
        test_original = series.iloc[-steps_eval:]              if n > steps_eval else series

        old_record = (
            db.query(ModelRegistry)
            .filter(ModelRegistry.kode_produk == kode_produk)
            .order_by(ModelRegistry.version.desc())
            .first()
        )
        mape_before = float(old_record.mape) if old_record and old_record.mape else None

        try:
            model_fit = auto_arima(
                train,
                d=None,
                max_d=2,
                seasonal=False,
                stepwise=True,
                information_criterion='aic',
                test='adf',
                error_action="ignore",
                suppress_warnings=True,
            )
        except Exception as e:
            db.add(TrainingLog(
                kode_produk=kode_produk,
                status="failed",
                mape_before=mape_before,
            ))
            db.commit()
            raise RuntimeError(f"Auto-ARIMA gagal untuk '{kode_produk}': {e}")

        preds_transformed = model_fit.predict(n_periods=len(test))
        preds_original    = self._inverse_boxcox(preds_transformed, boxcox_lambda, boxcox_shift)
        metrics           = self._compute_metrics(test_original.values, preds_original)

        new_version  = (old_record.version + 1) if old_record else 1
        safe_code    = str(kode_produk).replace("/", "_").replace("\\", "_")
        pkl_filename = f"model_{safe_code}_v{new_version}.pkl"
        pkl_path     = settings.MODELS_DIR / pkl_filename

        # shift berasal dari helper — tidak ada duplikasi kalkulasi
        bundle = {
            "model":         model_fit,
            "boxcox_lambda": boxcox_lambda,
            "boxcox_shift":  boxcox_shift,
        }
        joblib.dump(bundle, pkl_path)
        logger.info(
            f"Model saved: {pkl_path} "
            f"| boxcox_lambda={boxcox_lambda} | shift={boxcox_shift}"
        )

        db.add(ModelRegistry(
            kode_produk=kode_produk,
            file_path=str(pkl_path),
            version=new_version,
            rmse=metrics["rmse"],
            mape=metrics["mape"],
            arima_p=model_fit.order[0],
            arima_d=model_fit.order[1],
            arima_q=model_fit.order[2],
            prediction_count=0,
        ))
        db.add(TrainingLog(
            kode_produk=kode_produk,
            status="success",
            mape_before=mape_before,
            mape_after=metrics["mape"],
        ))
        db.commit()

        logger.info(
            f"Training selesai '{kode_produk}': "
            f"RMSE={metrics['rmse']} MAPE={metrics['mape']}% "
            f"order={model_fit.order} boxcox_lambda={boxcox_lambda}"
        )

        return {
            "kode_produk":    kode_produk,
            "version":        new_version,
            "order":          {
                "p": model_fit.order[0],
                "d": model_fit.order[1],
                "q": model_fit.order[2],
            },
            "n_observations": n,
            "metrics":        metrics,
            "pkl_path":       str(pkl_path),
            "boxcox_lambda":  boxcox_lambda,
        }

    # =========================================================================
    # predict_for_product — simpan ke DB
    # =========================================================================
    def predict_for_product(
        self,
        db: Session,
        kode_produk: str,
        steps: int = 1,
        confidence_level: float = 0.95,
    ) -> Dict[str, Any]:
        from app.models.prediction import PredictionResult

        model, record, boxcox_lambda, boxcox_shift = self._load_model_from_db(db, kode_produk)

        alpha    = 1 - confidence_level
        fc, conf = model.predict(n_periods=steps, return_conf_int=True, alpha=alpha)

        fc_original   = self._inverse_boxcox(np.array(fc),         boxcox_lambda, boxcox_shift)
        ci_lower_orig = self._inverse_boxcox(np.array(conf[:, 0]), boxcox_lambda, boxcox_shift)
        ci_upper_orig = self._inverse_boxcox(np.array(conf[:, 1]), boxcox_lambda, boxcox_shift)

        forecast_int = [math.ceil(max(v, 0)) for v in fc_original]
        ci_lower     = [math.ceil(max(v, 0)) for v in ci_lower_orig]
        ci_upper     = [math.ceil(max(v, 0)) for v in ci_upper_orig]

        series           = self._get_historical_data(db, kode_produk)
        last_data_date   = series.index.max().date()
        first_pred_month = last_data_date.replace(day=1) + relativedelta(months=1)
        prediction_dates = [
            first_pred_month + relativedelta(months=i) for i in range(steps)
        ]

        for i, pred_date in enumerate(prediction_dates):
            db.add(PredictionResult(
                kode_produk=kode_produk,
                tanggal_prediksi=pred_date,
                nilai_prediksi=forecast_int[i],
                confidence_lower=ci_lower[i],
                confidence_upper=ci_upper[i],
            ))
        db.commit()

        return {
            "kode_produk":      kode_produk,
            "model_version":    record.version,
            "steps":            steps,
            "confidence_level": confidence_level,
            "predictions": [
                {
                    "tanggal":          str(prediction_dates[i]),
                    "nilai_prediksi":   forecast_int[i],
                    "confidence_lower": ci_lower[i],
                    "confidence_upper": ci_upper[i],
                }
                for i in range(steps)
            ],
        }

    # =========================================================================
    # predict_for_product_raw — tanpa simpan ke DB
    # =========================================================================
    def predict_for_product_raw(
        self,
        db: Session,
        kode_produk: str,
        steps: int = 1,
        confidence_level: float = 0.95,
    ) -> Dict[str, Any]:
        model, record, boxcox_lambda, boxcox_shift = self._load_model_from_db(db, kode_produk)

        alpha    = 1 - confidence_level
        fc, conf = model.predict(n_periods=steps, return_conf_int=True, alpha=alpha)

        fc_original   = self._inverse_boxcox(np.array(fc),         boxcox_lambda, boxcox_shift)
        ci_lower_orig = self._inverse_boxcox(np.array(conf[:, 0]), boxcox_lambda, boxcox_shift)
        ci_upper_orig = self._inverse_boxcox(np.array(conf[:, 1]), boxcox_lambda, boxcox_shift)

        forecast_int = [math.ceil(max(v, 0)) for v in fc_original]
        ci_lower     = [math.ceil(max(v, 0)) for v in ci_lower_orig]
        ci_upper     = [math.ceil(max(v, 0)) for v in ci_upper_orig]

        series           = self._get_historical_data(db, kode_produk)
        last_data_date   = series.index.max().date()
        first_pred_month = last_data_date.replace(day=1) + relativedelta(months=1)
        prediction_dates = [
            first_pred_month + relativedelta(months=i) for i in range(steps)
        ]

        return {
            "kode_produk":      kode_produk,
            "model_version":    record.version,
            "steps":            steps,
            "confidence_level": confidence_level,
            "predictions": [
                {
                    "tanggal":          str(prediction_dates[i]),
                    "nilai_prediksi":   forecast_int[i],
                    "confidence_lower": ci_lower[i],
                    "confidence_upper": ci_upper[i],
                }
                for i in range(steps)
            ],
        }

    # =========================================================================
    # train_all & retrain_all
    # =========================================================================
    def train_all(self, db: Session) -> Dict[str, Any]:
        all_codes = self._get_all_kode_produk(db)
        results   = {"success": [], "failed": []}
        for kode_produk in all_codes:
            try:
                self.train_for_product(db, kode_produk)
                results["success"].append(kode_produk)
            except Exception as e:
                logger.warning(f"Skipping '{kode_produk}': {e}")
                results["failed"].append({"kode_produk": kode_produk, "error": str(e)})
        return results

    def retrain_all(self, db: Session) -> Dict[str, Any]:
        all_codes = self._get_all_kode_produk(db)
        if not all_codes:
            raise ValueError("Tidak ada data penjualan di database.")

        success_results, failed_results = [], []
        for kode_produk in all_codes:
            try:
                result = self.train_for_product(db, kode_produk)
                success_results.append(result)
            except Exception as e:
                logger.warning(f"Skipping '{kode_produk}': {e}")
                failed_results.append({"kode_produk": kode_produk, "error": str(e)})

        return {
            "total":         len(all_codes),
            "success_count": len(success_results),
            "failed_count":  len(failed_results),
            "results":       success_results,
            "failed":        failed_results,
        }

    def load_models_to_memory(self):
        logger.info("ML Service initialized (DB-first mode, Box-Cox enabled).")


ml_service = MLService()
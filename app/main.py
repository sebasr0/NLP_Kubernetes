from fastapi import FastAPI, HTTPException, APIRouter
from pydantic import BaseModel
from transformers import pipeline, Pipeline
from typing import List, Optional
import os
import threading
import json
from datetime import datetime
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Name of the HuggingFace model to download and cache during the Docker build
MODEL_NAME = os.getenv("MODEL_NAME", "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7")
# Directory (inside the container) where the weights/tokenizer will be stored
MODEL_DIR = os.getenv("MODEL_DIR", "/app/model")

# Fixed list of candidate labels
TOPICS = {
    "LABEL_0": "Analyst Update",
    "LABEL_1": "Fed | Central Banks",
    "LABEL_2": "Company | Product News",
    "LABEL_3": "Treasuries | Corporate Debt",
    "LABEL_4": "Dividend",
    "LABEL_5": "Earnings",
    "LABEL_6": "Energy | Oil",
    "LABEL_7": "Financials",
    "LABEL_8": "Currencies",
    "LABEL_9": "General News | Opinion",
    "LABEL_10": "Gold | Metals | Materials",
    "LABEL_11": "IPO",
    "LABEL_12": "Legal | Regulation",
    "LABEL_13": "M&A | Investments",
    "LABEL_14": "Macro",
    "LABEL_15": "Markets",
    "LABEL_16": "Politics",
    "LABEL_17": "Personnel Change",
    "LABEL_18": "Stock Commentary",
    "LABEL_19": "Stock Movement",
}

# ---------------------------------------------------------------------------
# Database configuration
# ---------------------------------------------------------------------------
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME")

DB_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
_engine = None

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(title="Zero-Shot Classification API", version="1.0.0")
router = APIRouter(prefix="/api")

# Pydantic models for request/response
class ClassifyRequest(BaseModel):
    text: str
    candidate_labels: Optional[List[str]] = None  # If omitted, default topics will be used
    multi_label: Optional[bool] = False           # Allow multiple correct classes

class ClassifyResponse(BaseModel):
    sequence: str
    labels: List[str]
    scores: List[float]

# ---------------------------------------------------------------------------
# Model loading (thread-safe, lazy)
# ---------------------------------------------------------------------------
_classifier: Optional[Pipeline] = None
_lock = threading.Lock()

def _load_model() -> Pipeline:
    """Lazy-load the HF pipeline once and cache it globally."""
    global _classifier
    if _classifier is None:
        with _lock:
            if _classifier is None:  # Double-checked locking
                _classifier = pipeline(
                    "zero-shot-classification",
                    model=MODEL_NAME,
                    tokenizer=MODEL_NAME,
                    cache_dir=MODEL_DIR,
                    device=-1,   # CPU; change to 0 for GPU
                )
    return _classifier

# Ensure the model is loaded during startup so first request isn't slow
@app.on_event("startup")
def _startup():
    global _engine
    _load_model()
    # Init DB connection & table
    try:
        _engine = create_engine(DB_URL, pool_pre_ping=True, pool_recycle=3600)
        with _engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS predictions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    input_text TEXT,
                    labels TEXT,
                    scores TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """))
    except Exception as e:
        # Log but do not crash the API if DB is unavailable
        print(f"[WARN] Could not connect/create table in MySQL: {e}")

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/healthz")
def healthz():
    """K8s readiness/liveness probe."""
    return {"status": "ok"}


@router.post("/classify", response_model=ClassifyResponse)
def classify(req: ClassifyRequest):
    if not req.text:
        raise HTTPException(status_code=400, detail="Field 'text' is required")

    classifier = _load_model()
    labels = req.candidate_labels or list(TOPICS.values())

    result = classifier(
        req.text,
        candidate_labels=labels,
        multi_label=req.multi_label,
    )

    # Persist prediction to MySQL (best-effort)
    try:
        if _engine is not None:
            with _engine.begin() as conn:
                conn.execute(
                    text("INSERT INTO predictions (input_text, labels, scores) VALUES (:t, :l, :s)"),
                    {
                        "t": req.text,
                        "l": json.dumps(result["labels"], ensure_ascii=False),
                        "s": json.dumps([float(s) for s in result["scores"]]),
                    },
                )
    except Exception as e:
        # Non-blocking log
        print(f"[WARN] Failed to insert prediction: {e}")

    # HuggingFace returns dict compatible with the response schema
    return ClassifyResponse(**result)


@router.get("/stats")
def get_stats():
    """Return aggregated statistics about predictions."""
    if _engine is None:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        with _engine.begin() as conn:
            total = conn.execute(text("SELECT COUNT(*) FROM predictions")).scalar()
            last_ts = conn.execute(text("SELECT MAX(created_at) FROM predictions")).scalar()
            rows = conn.execute(text("SELECT JSON_UNQUOTE(JSON_EXTRACT(labels, '$[0]')) AS label, COUNT(*) AS cnt FROM predictions GROUP BY label")).all()
            counts = {row.label: int(row.cnt) for row in rows}
        return {"total": int(total or 0), "last_timestamp": last_ts, "counts": counts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

# ---------------------------------------------------------------------------
# Register router
# ---------------------------------------------------------------------------
app.include_router(router)

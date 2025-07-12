# ---------- Zero-Shot Classification API Image ----------
# Base image with Python 3.11 (slim to keep size low)
FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Working directory inside the container
WORKDIR /app

# ---------------------------------------------------------------------------
# 1. Install dependencies
# ---------------------------------------------------------------------------
COPY requirements.txt ./requirements.txt

## Use a specific version of torch to avoid compatibility issues and cpu overload
ARG TORCH_VERSION=2.3.0
RUN pip install --no-cache-dir torch==${TORCH_VERSION}+cpu \
    -f https://download.pytorch.org/whl/torch_stable.html

RUN pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# 2. Copy application source
# ---------------------------------------------------------------------------
COPY . .

# ---------------------------------------------------------------------------
# 3. Download & cache the HF model during build (so runtime is instant)
# ---------------------------------------------------------------------------
# You can override MODEL_NAME at build time if needed:
#   docker build --build-arg MODEL_NAME=joeddav/xlm-roberta-large-xnli .
ARG MODEL_NAME=MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7
ENV MODEL_NAME=${MODEL_NAME}
ENV MODEL_DIR=/app/model

RUN python - <<'PY' \
&& rm -rf ~/.cache/huggingface
import os
from transformers import AutoModelForSequenceClassification, AutoTokenizer
model_name = os.environ.get("MODEL_NAME")
model_dir  = os.environ.get("MODEL_DIR")
print(f"[Docker] Downloading {model_name} to {model_dir} …")
AutoModelForSequenceClassification.from_pretrained(model_name, cache_dir=model_dir)
AutoTokenizer.from_pretrained(model_name, cache_dir=model_dir)
PY

# ---------------------------------------------------------------------------
# 4. Expose and run the app via Uvicorn
# ---------------------------------------------------------------------------
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

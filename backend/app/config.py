"""Configuration. SQLite by default so the demo runs anywhere with no
services; set DATABASE_URL to postgresql://... for production.
Redis is optional: REDIS_URL enables a real queue, otherwise jobs run
in-process via FastAPI BackgroundTasks (documented in ARCHITECTURE.md)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR / 'app.db'}")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
USE_LLM = bool(LLM_API_KEY)
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "50"))
ALLOWED_EXTS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".xlsx", ".xls", ".csv"}
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

"""Host-side scripts read the root .env (Compose settings) and reach the database on 127.0.0.1."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ here, /app in the image


def load() -> None:
    from dotenv import dotenv_values
    for key, value in dotenv_values(ENV_FILE).items():
        os.environ.setdefault(key, value or "")
    if not os.environ.get("DATABASE_URL") and os.environ.get("POSTGRES_PASSWORD"):
        os.environ["DATABASE_URL"] = (f"postgresql+psycopg://jobdots:{os.environ['POSTGRES_PASSWORD']}"
                                      f"@127.0.0.1:{os.environ.get('POSTGRES_PORT') or '55432'}/jobdots")


def set_env(name: str, value: str) -> None:
    """Add or replace NAME=value in the root .env without echoing it."""
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    lines = [line for line in lines if not line.startswith(f"{name}=")] + [f"{name}={value}"]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[name] = value

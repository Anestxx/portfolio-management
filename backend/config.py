from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


BASE_DIR = Path(__file__).resolve().parent.parent

if load_dotenv is not None:
    load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class AppConfig:
    base_dir: Path
    storage_dir: Path
    database_path: Path
    sample_data_path: Path
    schema_path: Path


def _resolve_path(path_value: str, fallback: Path) -> Path:
    raw_path = Path(path_value) if path_value else fallback
    return raw_path if raw_path.is_absolute() else BASE_DIR / raw_path


def get_config() -> AppConfig:
    storage_dir = _resolve_path(os.getenv("STORAGE_DIR", "storage"), BASE_DIR / "storage")
    database_path = _resolve_path(os.getenv("DATABASE_PATH", "storage/portfolio_manager.db"), storage_dir / "portfolio_manager.db")
    sample_data_path = _resolve_path(
        os.getenv("SAMPLE_DATA_PATH", "src/data/sample_portfolio.json"),
        BASE_DIR / "src/data/sample_portfolio.json",
    )
    schema_path = BASE_DIR / "data_query" / "db.sql"

    storage_dir.mkdir(parents=True, exist_ok=True)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    return AppConfig(
        base_dir=BASE_DIR,
        storage_dir=storage_dir,
        database_path=database_path,
        sample_data_path=sample_data_path,
        schema_path=schema_path,
    )

"""
Script manual para depurar el historial de `smart_weather.db`.

Uso (desde backend/):
    python scripts/cleanup_logs.py
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db import cleanup_logs, init_db  # noqa: E402


if __name__ == "__main__":
    init_db()
    result = cleanup_logs(delete_legacy=True, dedupe=True)
    print(
        "Depuración completada: "
        f"{result['deleted_legacy']} legados, "
        f"{result['deleted_duplicates']} duplicados, "
        f"{result['deleted_total']} total."
    )

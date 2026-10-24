from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RUNTIME_OVERLAY = ROOT / ".runtime312"
LEGACY_SITE_PACKAGES = ROOT.parent / ".venv" / "Lib" / "site-packages"

sys.path.insert(0, str(ROOT))
if RUNTIME_OVERLAY.is_dir():
    sys.path.insert(0, str(RUNTIME_OVERLAY))
elif LEGACY_SITE_PACKAGES.is_dir():
    sys.path.append(str(LEGACY_SITE_PACKAGES))

import uvicorn


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8765)

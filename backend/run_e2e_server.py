"""Start server for E2E tests."""
import os
import sys
from pathlib import Path

# Ensure we're running from backend directory
os.chdir(Path(__file__).resolve().parent)
sys.path.insert(0, ".")

os.environ["DATABASE_URL"] = "sqlite:///data/e2e_test.db"

import uvicorn
uvicorn.run("app.main:app", host="0.0.0.0", port=8000)

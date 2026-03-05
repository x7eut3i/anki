#!/usr/bin/env python3
"""
E2E Test Environment Setup

Creates a fresh database, imports content, creates test user,
and starts the server for Playwright E2E tests.

Usage:
  python setup_e2e.py          # Setup and start server
  python setup_e2e.py --setup  # Setup only (no server start)
  python setup_e2e.py --clean  # Clean up test data
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
CONTENT = ROOT / "content"
TEST_DB = BACKEND / "data" / "e2e_test.db"
VENV_PYTHON = BACKEND / ".venv" / "Scripts" / "python.exe"

if not VENV_PYTHON.exists():
    # Linux/Mac
    VENV_PYTHON = BACKEND / ".venv" / "bin" / "python"


def setup():
    """Create fresh test DB, import content, create test user."""
    print("🔧 Setting up E2E test environment...")

    # Remove old test DB
    if TEST_DB.exists():
        os.remove(TEST_DB)
        print(f"  🗑️  Removed old test DB: {TEST_DB}")

    env = {**os.environ, "DATABASE_URL": f"sqlite:///{TEST_DB}"}

    # Create test user
    print("  👤 Creating test user...")
    subprocess.run(
        [str(VENV_PYTHON), "manage_users.py", "add", "testuser", "test@example.com", "test123456", "--admin"],
        cwd=str(BACKEND),
        env=env,
        check=True,
    )

    # Import content
    print("  📥 Importing content...")
    subprocess.run(
        [str(VENV_PYTHON), str(CONTENT / "import_content.py"), "--db", str(TEST_DB)],
        cwd=str(CONTENT),
        env=env,
        check=True,
    )

    print("  ✅ E2E environment ready!")
    print(f"  💾 Test DB: {TEST_DB}")
    return env


def start_server(env):
    """Start uvicorn with the test database."""
    print(f"\n🚀 Starting server with test DB...")
    print(f"   DATABASE_URL=sqlite:///{TEST_DB}")
    print(f"   http://localhost:8000\n")

    try:
        subprocess.run(
            [str(VENV_PYTHON), "-m", "uvicorn", "app.main:app",
             "--host", "0.0.0.0", "--port", "8000", "--reload"],
            cwd=str(BACKEND),
            env=env,
        )
    except KeyboardInterrupt:
        print("\n⏹️  Server stopped.")


def clean():
    """Remove test database."""
    if TEST_DB.exists():
        os.remove(TEST_DB)
        print(f"🗑️  Removed test DB: {TEST_DB}")
    else:
        print("ℹ️  No test DB to clean.")


def main():
    parser = argparse.ArgumentParser(description="E2E Test Environment Manager")
    parser.add_argument("--setup", action="store_true", help="Setup only, don't start server")
    parser.add_argument("--clean", action="store_true", help="Remove test database")
    args = parser.parse_args()

    if args.clean:
        clean()
        return

    env = setup()

    if not args.setup:
        start_server(env)


if __name__ == "__main__":
    main()

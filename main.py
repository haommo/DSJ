"""
DSJ Automation Backend v2.0
===========================
Server API với phân quyền user (Admin/Staff/Customer)
Database: PostgreSQL

Chạy server:
    python main.py

Hoặc với uvicorn:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

import sys
import io
import asyncio

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn
from app.main import app

if __name__ == "__main__":
    print("""
    ============================================================
            DSJ Automation Backend Server v2.0
    ============================================================
      API Docs:     http://localhost:8000/docs
      ReDoc:        http://localhost:8000/redoc
      Health Check: http://localhost:8000/api/health
    ------------------------------------------------------------
      Default Admin: admin@dsj.com / admin123
      Roles: admin, staff, customer
    ============================================================
    """)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )

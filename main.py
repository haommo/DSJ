"""
DSJ Automation Backend
======================
Khoi chay server API de quan ly automation

Chay server:
    python main.py

Hoac voi uvicorn:
    uvicorn api:app --reload --host 0.0.0.0 --port 8000
"""

import sys
import io
import asyncio

# Fix Windows encoding issue
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    
    # Fix asyncio event loop policy for Playwright on Windows
    # Playwright requires subprocess support which is not available in default policy
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    print("[Windows] Set asyncio event loop policy to WindowsSelectorEventLoopPolicy")

import uvicorn
from api import app

if __name__ == "__main__":
    print("""
    ============================================================
               DSJ Automation Backend Server
    ============================================================
      API Docs:     http://localhost:8000/docs
      ReDoc:        http://localhost:8000/redoc
      Health Check: http://localhost:8000/api/health
    ============================================================
    """)
    
    uvicorn.run(
        app,  # Direct app object instead of string import
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )

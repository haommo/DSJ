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

# Fix Windows encoding issue
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

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
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Auto-reload khi code thay đổi
        log_level="info"
    )

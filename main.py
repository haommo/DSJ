"""
DSJ Automation Backend
======================
Khởi chạy server API để quản lý automation

Chạy server:
    python main.py

Hoặc với uvicorn:
    uvicorn api:app --reload --host 0.0.0.0 --port 8000
"""

import uvicorn
from api import app

if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║           DSJ Automation Backend Server                   ║
    ╠═══════════════════════════════════════════════════════════╣
    ║  API Docs:     http://localhost:8000/docs                 ║
    ║  ReDoc:        http://localhost:8000/redoc                ║
    ║  Health Check: http://localhost:8000/api/health           ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Auto-reload khi code thay đổi
        log_level="info"
    )

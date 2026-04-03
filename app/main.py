import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.database import engine, Base, SessionLocal
from app.models import User, UserRole, Task, TaskDetail, TaskStatus, ResultStatus
from app.services.auth_service import hash_password
from app.services.setting_service import seed_defaults
from app.routes import api_router

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Tạo tables
Base.metadata.create_all(bind=engine)

# Tạo thư mục screenshots
os.makedirs("screenshots", exist_ok=True)

# Rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: recovery tasks + tạo admin mặc định"""
    db = SessionLocal()
    try:
        user_count = db.query(User).count()
        if user_count == 0:
            admin = User(
                email="admin@dsj.com",
                hashed_password=hash_password("admin123"),
                full_name="Administrator",
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(admin)
            db.commit()
            logger.info("Created default admin: admin@dsj.com / admin123")

        seed_defaults(db)

        interrupted = db.query(Task).filter(Task.status == TaskStatus.RUNNING).all()
        for task in interrupted:
            task.status = TaskStatus.FAILED
            running_details = db.query(TaskDetail).filter(
                TaskDetail.task_id == task.id,
                TaskDetail.status == ResultStatus.RUNNING,
            ).all()
            for detail in running_details:
                detail.status = ResultStatus.FAILED
                detail.result_message = "Server bị crash khi đang chạy"
                task.failed_count += 1
            db.commit()
            logger.info(f"Task {task.task_code}: recovered")

        if interrupted:
            logger.info(f"Recovered {len(interrupted)} interrupted task(s)")

    except Exception as e:
        logger.error(f"Startup error: {e}")
        db.rollback()
    finally:
        db.close()

    yield


app = FastAPI(
    title="DSJ Automation API",
    description="API quản lý automation cho DSJ Exchange - Có phân quyền user",
    version="2.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount("/screenshots", StaticFiles(directory="screenshots"), name="screenshots")

# Routes
app.include_router(api_router)


@app.get("/api/health", tags=["System"])
def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

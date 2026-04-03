from fastapi import APIRouter
from app.routes.auth import router as auth_router
from app.routes.users import router as users_router
from app.routes.accounts import router as accounts_router
from app.routes.tasks import router as tasks_router
from app.routes.task_actions import router as task_actions_router
from app.routes.statistics import router as statistics_router
from app.routes.settings import router as settings_router

api_router = APIRouter(prefix="/api")

api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(accounts_router)
api_router.include_router(tasks_router)
api_router.include_router(task_actions_router)
api_router.include_router(statistics_router)
api_router.include_router(settings_router)

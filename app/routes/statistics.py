from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.user import User, UserRole
from app.models.account import Account
from app.models.task import Task, TaskDetail, ResultStatus
from app.schemas.task import Statistics
from app.dependencies import get_current_user
from app.services.account_service import get_customer_account_codes

router = APIRouter(prefix="/statistics", tags=["Statistics"])


@router.get("", response_model=Statistics)
def get_statistics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lấy thống kê tổng quan:
    - Admin/Staff: thống kê toàn bộ hệ thống
    - Customer: thống kê accounts của mình
    """
    if current_user.role == UserRole.CUSTOMER:
        account_codes = get_customer_account_codes(db, current_user)
        total_accounts = len(account_codes)

        if account_codes:
            task_ids = db.query(TaskDetail.task_id).filter(
                TaskDetail.account_code.in_(account_codes)
            ).distinct().all()
            task_ids = [t[0] for t in task_ids]
            total_tasks = len(task_ids)

            stats = db.query(
                func.count().label("total"),
                func.count().filter(TaskDetail.status == ResultStatus.SUCCESS).label("successful"),
                func.coalesce(func.sum(TaskDetail.balance).filter(TaskDetail.status == ResultStatus.SUCCESS), 0.0).label("balance"),
            ).filter(
                TaskDetail.account_code.in_(account_codes),
                TaskDetail.status.in_([ResultStatus.SUCCESS, ResultStatus.FAILED]),
            ).first()

            total_results = stats.total
            successful = stats.successful
            total_balance = float(stats.balance)
        else:
            total_tasks = 0
            total_results = 0
            successful = 0
            total_balance = 0.0
    else:
        total_accounts = db.query(func.count(Account.id)).scalar()
        total_tasks = db.query(func.count(Task.id)).scalar()

        stats = db.query(
            func.count().label("total"),
            func.count().filter(TaskDetail.status == ResultStatus.SUCCESS).label("successful"),
            func.coalesce(func.sum(TaskDetail.balance).filter(TaskDetail.status == ResultStatus.SUCCESS), 0.0).label("balance"),
        ).filter(
            TaskDetail.status.in_([ResultStatus.SUCCESS, ResultStatus.FAILED]),
        ).first()

        total_results = stats.total
        successful = stats.successful
        total_balance = float(stats.balance)

    success_rate = (successful / total_results * 100) if total_results > 0 else 100.0

    return Statistics(
        total_balance=round(total_balance, 2),
        total_accounts=total_accounts,
        total_tasks=total_tasks,
        success_rate=round(success_rate, 1),
    )

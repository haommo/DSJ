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
    if current_user.role in (UserRole.CUSTOMER, UserRole.STAFF):
        account_codes = get_customer_account_codes(db, current_user)
        total_accounts = len(account_codes)

        if account_codes:
            total_tasks = db.query(func.count(func.distinct(TaskDetail.task_id))).filter(
                TaskDetail.account_code.in_(account_codes)
            ).scalar()

            # Lấy balance từ task mới nhất
            latest_task = db.query(Task).join(TaskDetail).filter(
                TaskDetail.account_code.in_(account_codes)
            ).order_by(Task.created_at.desc()).first()

            if latest_task:
                total_balance = float(db.query(
                    func.coalesce(func.sum(TaskDetail.balance), 0.0)
                ).filter(
                    TaskDetail.task_id == latest_task.id,
                    TaskDetail.account_code.in_(account_codes),
                    TaskDetail.status == ResultStatus.SUCCESS,
                ).scalar())
            else:
                total_balance = 0.0

            # Thống kê success rate từ tất cả task
            stats = db.query(
                func.count().label("total"),
                func.count().filter(TaskDetail.status == ResultStatus.SUCCESS).label("successful"),
            ).filter(
                TaskDetail.account_code.in_(account_codes),
                TaskDetail.status.in_([ResultStatus.SUCCESS, ResultStatus.FAILED]),
            ).first()

            total_results = stats.total
            successful = stats.successful
        else:
            total_tasks = 0
            total_results = 0
            successful = 0
            total_balance = 0.0
    else:
        total_accounts = db.query(func.count(Account.id)).scalar()
        total_tasks = db.query(func.count(Task.id)).scalar()

        # Lấy balance từ task mới nhất
        latest_task = db.query(Task).order_by(Task.created_at.desc()).first()

        if latest_task:
            total_balance = float(db.query(
                func.coalesce(func.sum(TaskDetail.balance), 0.0)
            ).filter(
                TaskDetail.task_id == latest_task.id,
                TaskDetail.status == ResultStatus.SUCCESS,
            ).scalar())
        else:
            total_balance = 0.0

        # Thống kê success rate từ tất cả task
        stats = db.query(
            func.count().label("total"),
            func.count().filter(TaskDetail.status == ResultStatus.SUCCESS).label("successful"),
        ).filter(
            TaskDetail.status.in_([ResultStatus.SUCCESS, ResultStatus.FAILED]),
        ).first()

        total_results = stats.total
        successful = stats.successful

    success_rate = (successful / total_results * 100) if total_results > 0 else 100.0

    return Statistics(
        total_balance=round(total_balance, 2),
        total_accounts=total_accounts,
        total_tasks=total_tasks,
        success_rate=round(success_rate, 1),
    )

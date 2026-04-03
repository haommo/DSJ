from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime
import json
import asyncio

from app.database import get_db, SessionLocal
from app.models.user import User, UserRole
from app.models.account import Account
from app.models.task import Task, TaskDetail, TaskStatus, ResultStatus
from app.schemas.task import TaskDetailItem
from app.dependencies import get_current_user, require_roles

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post("/{task_id}/cancel")
def cancel_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.STAFF)),
):
    """Hủy task đang chạy"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Task is not running")

    from app.services.task_manager import task_manager
    task_manager.cancel_task(task_id)
    return {"message": "Task cancelled"}


@router.post("/{task_id}/retry/{detail_id}")
async def retry_task_detail(
    task_id: int,
    detail_id: int,
    headless: bool = True,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.STAFF)),
):
    """Chạy lại một account cụ thể trong task"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Cannot retry while task is running")

    detail = db.query(TaskDetail).filter(
        TaskDetail.id == detail_id, TaskDetail.task_id == task_id
    ).first()
    if not detail:
        raise HTTPException(status_code=404, detail="Task detail not found")
    if detail.status not in [ResultStatus.FAILED, ResultStatus.PENDING]:
        raise HTTPException(status_code=400, detail=f"Can only retry failed/pending. Current: {detail.status}")

    if detail.status == ResultStatus.FAILED:
        task.failed_count = max(0, task.failed_count - 1)

    detail.status = ResultStatus.PENDING
    detail.result_message = None
    detail.balance = None
    detail.screenshot_path = None
    db.commit()

    from app.services.task_manager import task_manager
    background_tasks.add_task(task_manager.retry_single_detail, task_id, detail_id, headless)
    return {"message": f"Retrying account {detail.account_code}"}


@router.post("/{task_id}/retry-all")
async def retry_all_failed(
    task_id: int,
    headless: bool = True,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.STAFF)),
):
    """Chạy lại tất cả accounts failed trong task"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Task is already running")

    failed_details = db.query(TaskDetail).filter(
        TaskDetail.task_id == task_id, TaskDetail.status == ResultStatus.FAILED
    ).all()
    if not failed_details:
        return {"message": "No failed accounts to retry", "count": 0}

    for detail in failed_details:
        detail.status = ResultStatus.PENDING
        detail.result_message = None
        detail.balance = None
        detail.screenshot_path = None
        task.failed_count -= 1
    db.commit()

    from app.services.task_manager import task_manager
    background_tasks.add_task(task_manager.run_task, task_id, headless)
    return {"message": f"Retrying {len(failed_details)} failed accounts", "count": len(failed_details)}


@router.post("/{task_id}/resume")
async def resume_task(
    task_id: int,
    headless: bool = True,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.STAFF)),
):
    """Tiếp tục chạy task với các accounts pending/failed"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Task is already running")

    pending = db.query(TaskDetail).filter(
        TaskDetail.task_id == task_id,
        TaskDetail.status.in_([ResultStatus.PENDING, ResultStatus.FAILED]),
    ).all()
    if not pending:
        return {"message": "No pending accounts to run", "count": 0}

    for detail in pending:
        if detail.status == ResultStatus.FAILED:
            detail.status = ResultStatus.PENDING
            detail.result_message = None
            detail.balance = None
            detail.screenshot_path = None
            task.failed_count -= 1
    db.commit()

    from app.services.task_manager import task_manager
    background_tasks.add_task(task_manager.run_task, task_id, headless)
    return {"message": f"Resuming with {len(pending)} accounts", "count": len(pending)}


@router.get("/{task_id}/stream")
async def stream_task_progress(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stream realtime progress của task qua SSE"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    MAX_SSE_DURATION = 600  # 10 minutes
    HEARTBEAT_INTERVAL = 15  # seconds

    async def event_generator():
        last_success, last_failed = -1, -1
        start_time = asyncio.get_event_loop().time()
        tick = 0
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > MAX_SSE_DURATION:
                yield f"data: {json.dumps({'event': 'timeout', 'message': 'SSE connection timeout'})}\n\n"
                break

            session = SessionLocal()
            try:
                t = session.query(Task).filter(Task.id == task_id).first()
                if not t:
                    yield f"data: {json.dumps({'error': 'Task not found'})}\n\n"
                    break

                if t.success_count != last_success or t.failed_count != last_failed:
                    last_success, last_failed = t.success_count, t.failed_count
                    data = {
                        "task_id": t.id, "status": t.status,
                        "total_accounts": t.total_accounts,
                        "success_count": t.success_count, "failed_count": t.failed_count,
                        "total_balance": t.total_balance,
                        "progress": round((t.success_count + t.failed_count) / max(t.total_accounts, 1) * 100, 1),
                    }
                    yield f"data: {json.dumps(data)}\n\n"
                elif tick % HEARTBEAT_INTERVAL == 0:
                    yield f": heartbeat\n\n"

                if t.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                    yield f"data: {json.dumps({'event': 'completed', 'status': t.status})}\n\n"
                    break
            finally:
                session.close()
            tick += 1
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )

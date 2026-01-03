import sys
import asyncio

# Fix Windows asyncio event loop policy for Playwright
# MUST be set before any async operations
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    print("[Windows] Set asyncio event loop policy to WindowsSelectorEventLoopPolicy")

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime
import json
import os

from database import engine, get_db, Base
from models import Account, Task, TaskDetail, TaskStatus, ResultStatus
from schemas import (
    AccountCreate, AccountUpdate, AccountResponse,
    TaskCreate, TaskResponse, TaskDetailResponse, TaskDetailItem,
    Statistics, PaginationMeta, TaskListResponse
)
from task_manager import task_manager

# Tạo tables
Base.metadata.create_all(bind=engine)

# Tạo thư mục screenshots
os.makedirs("screenshots", exist_ok=True)

app = FastAPI(
    title="DSJ Automation API",
    description="API quản lý automation cho DSJ Exchange",
    version="1.0.0"
)


# ============== STARTUP EVENT - RECOVERY ==============

@app.on_event("startup")
async def startup_event():
    """
    Recovery mechanism khi server khởi động.
    Xử lý các tasks bị interrupted do server crash.
    - Task RUNNING -> FAILED (để có thể resume)
    - Detail RUNNING -> FAILED (cần retry)
    - Detail PENDING -> giữ nguyên PENDING (để resume tiếp)
    """
    from database import SessionLocal
    
    db = SessionLocal()
    try:
        # Tìm các tasks đang RUNNING (bị interrupted)
        interrupted_tasks = db.query(Task).filter(Task.status == TaskStatus.RUNNING).all()
        
        for task in interrupted_tasks:
            # Đánh dấu task là FAILED để có thể resume
            task.status = TaskStatus.FAILED
            
            # Chỉ cập nhật các details đang RUNNING thành FAILED
            # PENDING giữ nguyên để có thể resume
            running_details = db.query(TaskDetail).filter(
                TaskDetail.task_id == task.id,
                TaskDetail.status == ResultStatus.RUNNING
            ).all()
            
            for detail in running_details:
                detail.status = ResultStatus.FAILED
                detail.result_message = "Server bị crash khi đang chạy"
                task.failed_count += 1
            
            # Đếm số PENDING còn lại
            pending_count = db.query(TaskDetail).filter(
                TaskDetail.task_id == task.id,
                TaskDetail.status == ResultStatus.PENDING
            ).count()
            
            db.commit()
            print(f"[RECOVERY] Task {task.task_code}: {len(running_details)} running -> failed, {pending_count} pending accounts remaining")
        
        if interrupted_tasks:
            print(f"[RECOVERY] Recovered {len(interrupted_tasks)} interrupted task(s)")
            print(f"[RECOVERY] Use POST /api/tasks/{{id}}/resume to continue running pending accounts")
        else:
            print("[RECOVERY] No interrupted tasks found")
            
    except Exception as e:
        print(f"[RECOVERY] Error during recovery: {e}")
        db.rollback()
    finally:
        db.close()


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files cho screenshots
app.mount("/screenshots", StaticFiles(directory="screenshots"), name="screenshots")


# ============== 1. API QUẢN LÝ TÀI KHOẢN ==============

@app.get("/api/accounts", response_model=List[AccountResponse], tags=["Accounts"])
def get_accounts(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Lấy danh sách tài khoản"""
    return db.query(Account).offset(skip).limit(limit).all()


@app.get("/api/accounts/{account_id}", response_model=AccountResponse, tags=["Accounts"])
def get_account(account_id: int, db: Session = Depends(get_db)):
    """Lấy thông tin một tài khoản"""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@app.post("/api/accounts", response_model=AccountResponse, tags=["Accounts"])
def create_account(account: AccountCreate, db: Session = Depends(get_db)):
    """Thêm tài khoản mới"""
    # Kiểm tra account_code đã tồn tại
    existing = db.query(Account).filter(Account.account_code == account.account_code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Account code already exists")
    
    # Kiểm tra email đã tồn tại
    existing_email = db.query(Account).filter(Account.email == account.email).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already exists")
    
    db_account = Account(**account.dict())
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account


@app.put("/api/accounts/{account_id}", response_model=AccountResponse, tags=["Accounts"])
def update_account(account_id: int, account: AccountUpdate, db: Session = Depends(get_db)):
    """Sửa tài khoản"""
    db_account = db.query(Account).filter(Account.id == account_id).first()
    if not db_account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    update_data = account.dict(exclude_unset=True)
    
    # Kiểm tra trùng account_code
    if "account_code" in update_data and update_data["account_code"] != db_account.account_code:
        existing = db.query(Account).filter(Account.account_code == update_data["account_code"]).first()
        if existing:
            raise HTTPException(status_code=400, detail="Account code already exists")
    
    # Kiểm tra trùng email
    if "email" in update_data and update_data["email"] != db_account.email:
        existing = db.query(Account).filter(Account.email == update_data["email"]).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already exists")
    
    for key, value in update_data.items():
        setattr(db_account, key, value)
    
    db.commit()
    db.refresh(db_account)
    return db_account


@app.delete("/api/accounts/{account_id}", tags=["Accounts"])
def delete_account(account_id: int, db: Session = Depends(get_db)):
    """Xóa tài khoản"""
    db_account = db.query(Account).filter(Account.id == account_id).first()
    if not db_account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    db.delete(db_account)
    db.commit()
    return {"message": "Account deleted successfully"}


# ============== 2. API THỐNG KÊ ==============

@app.get("/api/statistics", response_model=Statistics, tags=["Statistics"])
def get_statistics(db: Session = Depends(get_db)):
    """
    Lấy thống kê tổng quan:
    - Tổng số dư: Lấy từ task có total_balance lớn nhất
    - Tổng tài khoản
    - Tổng task
    - Tỷ lệ thành công
    """
    # Tổng số dư = total_balance của task có balance cao nhất
    max_balance_task = db.query(Task).order_by(Task.total_balance.desc()).first()
    total_balance = max_balance_task.total_balance if max_balance_task else 0.0
    
    # Tổng tài khoản
    total_accounts = db.query(Account).count()
    
    # Tổng task
    total_tasks = db.query(Task).count()
    
    # Tính tỷ lệ thành công
    total_results = db.query(TaskDetail).filter(
        TaskDetail.status.in_([ResultStatus.SUCCESS, ResultStatus.FAILED])
    ).count()
    successful_results = db.query(TaskDetail).filter(
        TaskDetail.status == ResultStatus.SUCCESS
    ).count()
    
    success_rate = (successful_results / total_results * 100) if total_results > 0 else 100.0
    
    return Statistics(
        total_balance=round(total_balance, 2),
        total_accounts=total_accounts,
        total_tasks=total_tasks,
        success_rate=round(success_rate, 1)
    )


# ============== API CLEANUP INCOMPLETE TASKS ==============

@app.get("/api/tasks/incomplete", tags=["Tasks"])
def get_incomplete_tasks(db: Session = Depends(get_db)):
    """
    Lấy danh sách các tasks bị incomplete (số details ít hơn total_accounts).
    Thường xảy ra khi server crash giữa chừng khi tạo task.
    """
    tasks = db.query(Task).all()
    incomplete = []
    
    for task in tasks:
        detail_count = db.query(TaskDetail).filter(TaskDetail.task_id == task.id).count()
        if detail_count < task.total_accounts:
            incomplete.append({
                "id": task.id,
                "task_code": task.task_code,
                "status": task.status,
                "total_accounts": task.total_accounts,
                "actual_details": detail_count,
                "missing": task.total_accounts - detail_count
            })
    
    return {"incomplete_tasks": incomplete, "count": len(incomplete)}


@app.post("/api/tasks/{task_id}/repair", tags=["Tasks"])
def repair_incomplete_task(task_id: int, db: Session = Depends(get_db)):
    """
    Sửa task incomplete bằng cách thêm các accounts còn thiếu.
    Chỉ thêm accounts chưa có trong task.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Không cho phép repair task đang chạy
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Cannot repair running task")
    
    # Lấy account_codes đã có trong task
    existing_codes = db.query(TaskDetail.account_code).filter(
        TaskDetail.task_id == task_id
    ).all()
    existing_codes = [code[0] for code in existing_codes]
    
    # Lấy tất cả accounts chưa có trong task
    missing_accounts = db.query(Account).filter(
        ~Account.account_code.in_(existing_codes)
    ).all()
    
    if not missing_accounts:
        return {"message": "No missing accounts to add", "added": 0}
    
    # Thêm các accounts còn thiếu
    added_count = 0
    for account in missing_accounts:
        if len(existing_codes) + added_count >= task.total_accounts:
            break
        
        task_detail = TaskDetail(
            task_id=task_id,
            account_code=account.account_code,
            status=ResultStatus.PENDING
        )
        db.add(task_detail)
        added_count += 1
    
    db.commit()
    
    return {
        "message": f"Added {added_count} missing accounts",
        "added": added_count,
        "task_id": task_id
    }


@app.delete("/api/tasks/{task_id}/force", tags=["Tasks"])
def force_delete_task(task_id: int, db: Session = Depends(get_db)):
    """
    Xóa task bất kể trạng thái (kể cả running).
    Dùng cho trường hợp task bị lỗi không thể xử lý.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task_code = task.task_code
    
    # Xóa tất cả task details
    db.query(TaskDetail).filter(TaskDetail.task_id == task_id).delete()
    
    # Xóa task
    db.delete(task)
    db.commit()
    
    return {"message": f"Task {task_code} force deleted successfully"}


# ============== 3. API TẠO TASK & CANCEL TASK ==============

@app.post("/api/tasks", response_model=TaskResponse, tags=["Tasks"])
async def create_task(
    task_data: TaskCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Tạo task mới và khởi chạy automation
    - Nếu account_ids được chỉ định: chạy cho các accounts đó
    - Nếu không: chạy cho tất cả accounts
    """
    # Kiểm tra task code đã tồn tại
    existing = db.query(Task).filter(Task.task_code == task_data.task_code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Task code already exists")
    
    # Lấy danh sách accounts
    if task_data.account_ids:
        accounts = db.query(Account).filter(Account.id.in_(task_data.account_ids)).all()
    else:
        accounts = db.query(Account).all()
    
    if not accounts:
        raise HTTPException(status_code=400, detail="No accounts available")
    
    try:
        # Tạo task
        db_task = Task(
            task_code=task_data.task_code,
            status=TaskStatus.PENDING,
            total_accounts=len(accounts),
            success_count=0,
            failed_count=0,
            total_balance=0.0
        )
        db.add(db_task)
        db.flush()  # Lấy ID mà không commit
        
        # Tạo task details cho mỗi account
        for account in accounts:
            task_detail = TaskDetail(
                task_id=db_task.id,
                account_code=account.account_code,
                status=ResultStatus.PENDING
            )
            db.add(task_detail)
        
        # Commit tất cả cùng lúc (atomic transaction)
        db.commit()
        db.refresh(db_task)
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create task: {str(e)}")
    
    # Khởi chạy automation trong background
    background_tasks.add_task(run_task_background, db_task.id, task_data.headless)
    
    return db_task


async def run_task_background(task_id: int, headless: bool = True):
    """Chạy task trong background"""
    await task_manager.run_task(task_id, headless=headless)


@app.post("/api/tasks/{task_id}/cancel", tags=["Tasks"])
def cancel_task(task_id: int, db: Session = Depends(get_db)):
    """Hủy task đang chạy"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status != TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Task is not running")
    
    task_manager.cancel_task(task_id)
    return {"message": "Task cancelled"}


@app.delete("/api/tasks/{task_id}", tags=["Tasks"])
def delete_task(task_id: int, db: Session = Depends(get_db)):
    """
    Xóa task và tất cả task details liên quan.
    Không cho phép xóa task đang chạy.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Không cho phép xóa task đang chạy
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Cannot delete running task. Cancel it first.")
    
    # Xóa tất cả task details trước
    db.query(TaskDetail).filter(TaskDetail.task_id == task_id).delete()
    
    # Xóa task
    db.delete(task)
    db.commit()
    
    return {"message": f"Task {task.task_code} deleted successfully"}


@app.post("/api/tasks/{task_id}/retry/{detail_id}", tags=["Tasks"])
async def retry_task_detail(
    task_id: int,
    detail_id: int,
    headless: bool = True,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """
    Chạy lại một account cụ thể trong task.
    Cho phép retry khi account có status FAILED hoặc PENDING (task bị crash).
    Chỉ cho phép retry khi task không đang chạy.
    
    Params:
    - headless: True = ẩn browser, False = hiển thị browser
    """
    # Kiểm tra task tồn tại
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Không cho phép retry khi task đang chạy
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Cannot retry while task is running")
    
    # Kiểm tra detail tồn tại và thuộc task
    detail = db.query(TaskDetail).filter(
        TaskDetail.id == detail_id,
        TaskDetail.task_id == task_id
    ).first()
    if not detail:
        raise HTTPException(status_code=404, detail="Task detail not found")
    
    # Cho phép retry nếu FAILED hoặc PENDING (task crash khi chưa chạy đến account này)
    if detail.status not in [ResultStatus.FAILED, ResultStatus.PENDING]:
        raise HTTPException(
            status_code=400, 
            detail=f"Can only retry failed or pending accounts. Current status: {detail.status}"
        )
    
    # Nếu đang FAILED, giảm failed_count của task
    if detail.status == ResultStatus.FAILED:
        task.failed_count = max(0, task.failed_count - 1)
    
    # Reset trạng thái
    detail.status = ResultStatus.PENDING
    detail.result_message = None
    detail.balance = None
    detail.screenshot_path = None
    db.commit()
    
    # Chạy lại trong background
    background_tasks.add_task(retry_single_account, task_id, detail_id, headless)
    
    return {"message": f"Retrying account {detail.account_code}"}


async def retry_single_account(task_id: int, detail_id: int, headless: bool = True):
    """Chạy lại automation cho một account cụ thể"""
    await task_manager.retry_single_detail(task_id, detail_id, headless=headless)


@app.post("/api/tasks/{task_id}/retry-all", tags=["Tasks"])
async def retry_all_failed(
    task_id: int,
    headless: bool = True,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """
    Chạy lại TẤT CẢ accounts đã failed trong task.
    Task sẽ được đặt lại trạng thái RUNNING.
    
    Params:
    - headless: True = ẩn browser, False = hiển thị browser
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Task is already running")
    
    # Lấy tất cả accounts failed
    failed_details = db.query(TaskDetail).filter(
        TaskDetail.task_id == task_id,
        TaskDetail.status == ResultStatus.FAILED
    ).all()
    
    if not failed_details:
        return {"message": "No failed accounts to retry", "count": 0}
    
    # Reset tất cả failed accounts về PENDING
    for detail in failed_details:
        detail.status = ResultStatus.PENDING
        detail.result_message = None
        detail.balance = None
        detail.screenshot_path = None
        task.failed_count -= 1  # Giảm failed count
    
    db.commit()
    
    # Chạy lại task trong background
    background_tasks.add_task(resume_task_background, task_id, headless)
    
    return {
        "message": f"Retrying {len(failed_details)} failed accounts",
        "count": len(failed_details),
        "accounts": [d.account_code for d in failed_details]
    }


@app.post("/api/tasks/{task_id}/resume", tags=["Tasks"])
async def resume_task(
    task_id: int,
    headless: bool = True,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """
    Tiếp tục chạy task - chạy tất cả accounts có status PENDING hoặc FAILED.
    Dùng sau khi server crash để tiếp tục chạy các accounts chưa hoàn thành.
    
    Params:
    - headless: True = ẩn browser, False = hiển thị browser
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Task is already running")
    
    # Lấy tất cả accounts chưa hoàn thành (PENDING hoặc FAILED)
    pending_details = db.query(TaskDetail).filter(
        TaskDetail.task_id == task_id,
        TaskDetail.status.in_([ResultStatus.PENDING, ResultStatus.FAILED])
    ).all()
    
    if not pending_details:
        return {"message": "No pending accounts to run", "count": 0}
    
    # Reset các FAILED về PENDING
    for detail in pending_details:
        if detail.status == ResultStatus.FAILED:
            detail.status = ResultStatus.PENDING
            detail.result_message = None
            detail.balance = None
            detail.screenshot_path = None
            task.failed_count -= 1
    
    db.commit()
    
    # Chạy task trong background
    background_tasks.add_task(resume_task_background, task_id, headless)
    
    return {
        "message": f"Resuming task with {len(pending_details)} accounts",
        "count": len(pending_details),
        "accounts": [d.account_code for d in pending_details]
    }


async def resume_task_background(task_id: int, headless: bool = True):
    """Tiếp tục chạy task cho các accounts PENDING"""
    await task_manager.run_task(task_id, headless=headless)


# ============== 4. API DANH SÁCH TASK & CHI TIẾT ==============

@app.get("/api/tasks", response_model=TaskListResponse, tags=["Tasks"])
def get_tasks(
    page: int = 1,
    page_size: int = 5,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Lấy danh sách tasks kèm chi tiết tất cả accounts.
    
    Params:
    - page: Số trang (mặc định: 1)
    - page_size: Số items mỗi trang (mặc định: 5)
    - status: Lọc theo trạng thái (pending, running, completed, failed)
    """
    # Validate page
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 5
    if page_size > 100:
        page_size = 100
    
    # Base query
    query = db.query(Task).order_by(Task.created_at.desc())
    if status:
        query = query.filter(Task.status == status)
    
    # Đếm tổng số records
    total_items = query.count()
    total_pages = (total_items + page_size - 1) // page_size  # Làm tròn lên
    
    # Phân trang
    skip = (page - 1) * page_size
    tasks = query.offset(skip).limit(page_size).all()
    
    # Build response
    result = []
    for task in tasks:
        # Lấy details cho mỗi task
        details = db.query(TaskDetail).filter(TaskDetail.task_id == task.id).all()
        
        detail_items = []
        for d in details:
            # Lấy email từ bảng Account
            account = db.query(Account).filter(Account.account_code == d.account_code).first()
            email = account.email if account else None
            
            detail_items.append(TaskDetailItem(
                id=d.id,
                account_code=d.account_code,
                email=email,
                balance=d.balance,
                status=d.status,
                result_message=d.result_message,
                screenshot_path=d.screenshot_path
            ))
        
        result.append(TaskDetailResponse(
            id=task.id,
            task_code=task.task_code,
            status=task.status,
            total_accounts=task.total_accounts,
            success_count=task.success_count,
            failed_count=task.failed_count,
            total_balance=task.total_balance,
            created_at=task.created_at,
            updated_at=task.updated_at,
            details=detail_items
        ))
    
    # Pagination meta
    pagination = PaginationMeta(
        page=page,
        page_size=page_size,
        total_items=total_items,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1
    )
    
    return TaskListResponse(data=result, pagination=pagination)


@app.get("/api/tasks/{task_id}", response_model=TaskDetailResponse, tags=["Tasks"])
def get_task_detail(task_id: int, db: Session = Depends(get_db)):
    """
    Lấy chi tiết task với kết quả từng account
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Lấy details
    details = db.query(TaskDetail).filter(TaskDetail.task_id == task_id).all()
    
    detail_items = []
    for d in details:
        # Lấy email từ bảng Account
        account = db.query(Account).filter(Account.account_code == d.account_code).first()
        email = account.email if account else None
        
        detail_items.append(TaskDetailItem(
            id=d.id,
            account_code=d.account_code,
            email=email,
            balance=d.balance,
            status=d.status,
            result_message=d.result_message,
            screenshot_path=d.screenshot_path
        ))
    
    return TaskDetailResponse(
        id=task.id,
        task_code=task.task_code,
        status=task.status,
        total_accounts=task.total_accounts,
        success_count=task.success_count,
        failed_count=task.failed_count,
        total_balance=task.total_balance,
        created_at=task.created_at,
        updated_at=task.updated_at,
        details=detail_items
    )


# ============== 5. REALTIME STREAM (SSE) ==============

@app.get("/api/tasks/{task_id}/stream", tags=["Tasks"])
async def stream_task_progress(task_id: int, db: Session = Depends(get_db)):
    """
    Stream realtime progress của task qua Server-Sent Events (SSE).
    Client có thể listen để nhận updates sau mỗi account chạy xong.
    
    Usage (JavaScript):
    ```
    const eventSource = new EventSource('/api/tasks/1/stream');
    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log(data);
    };
    ```
    """
    # Kiểm tra task tồn tại
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    async def event_generator():
        """Generator để stream events"""
        last_success = -1
        last_failed = -1
        
        while True:
            # Lấy database session mới mỗi lần query
            from database import SessionLocal
            session = SessionLocal()
            
            try:
                # Query task mới nhất
                current_task = session.query(Task).filter(Task.id == task_id).first()
                
                if not current_task:
                    yield f"data: {json.dumps({'error': 'Task not found'})}\n\n"
                    break
                
                # Kiểm tra có thay đổi không
                if (current_task.success_count != last_success or 
                    current_task.failed_count != last_failed):
                    
                    last_success = current_task.success_count
                    last_failed = current_task.failed_count
                    
                    # Lấy detail mới nhất đã hoàn thành
                    latest_detail = session.query(TaskDetail).filter(
                        TaskDetail.task_id == task_id,
                        TaskDetail.status.in_([ResultStatus.SUCCESS, ResultStatus.FAILED])
                    ).order_by(TaskDetail.id.desc()).first()
                    
                    # Build response data
                    data = {
                        "task_id": current_task.id,
                        "task_code": current_task.task_code,
                        "status": current_task.status,
                        "total_accounts": current_task.total_accounts,
                        "success_count": current_task.success_count,
                        "failed_count": current_task.failed_count,
                        "pending_count": current_task.total_accounts - current_task.success_count - current_task.failed_count,
                        "total_balance": current_task.total_balance,
                        "progress": round((current_task.success_count + current_task.failed_count) / max(current_task.total_accounts, 1) * 100, 1),
                        "latest_account": None
                    }
                    
                    if latest_detail:
                        data["latest_account"] = {
                            "id": latest_detail.id,
                            "account_code": latest_detail.account_code,
                            "status": latest_detail.status,
                            "balance": latest_detail.balance,
                            "result_message": latest_detail.result_message
                        }
                    
                    yield f"data: {json.dumps(data)}\n\n"
                
                # Nếu task hoàn thành, gửi final event và đóng
                if current_task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                    final_data = {
                        "event": "completed",
                        "task_id": current_task.id,
                        "status": current_task.status,
                        "success_count": current_task.success_count,
                        "failed_count": current_task.failed_count,
                        "total_balance": current_task.total_balance
                    }
                    yield f"data: {json.dumps(final_data)}\n\n"
                    break
                    
            finally:
                session.close()
            
            # Đợi 1 giây trước khi check lại
            await asyncio.sleep(1)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


# ============== Health Check ==============

@app.get("/api/health", tags=["System"])
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


# ============== 6. REALTIME TASK LIST STREAM (SSE) ==============

@app.get("/api/tasks/stream", tags=["Tasks"])
async def stream_tasks_list():
    """
    Stream realtime danh sách tasks qua Server-Sent Events (SSE).
    Gửi update khi có task mới hoặc task thay đổi trạng thái.
    
    Usage (JavaScript):
    ```javascript
    const eventSource = new EventSource('/api/tasks/stream');
    
    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log('Tasks updated:', data);
        // data.tasks - mảng các tasks
        // data.event - loại event: 'initial', 'update', 'new_task'
    };
    
    eventSource.onerror = (error) => {
        console.error('SSE error:', error);
        eventSource.close();
    };
    ```
    """
    async def event_generator():
        """Generator để stream task list updates"""
        from database import SessionLocal
        
        last_task_count = -1
        last_states = {}  # {task_id: (status, success_count, failed_count)}
        
        while True:
            session = SessionLocal()
            
            try:
                # Lấy tất cả tasks (giới hạn 50 task gần nhất)
                tasks = session.query(Task).order_by(Task.created_at.desc()).limit(50).all()
                
                current_states = {}
                has_changes = False
                event_type = "update"
                
                # Check số lượng task thay đổi (task mới)
                if len(tasks) != last_task_count:
                    has_changes = True
                    if last_task_count == -1:
                        event_type = "initial"
                    else:
                        event_type = "new_task"
                    last_task_count = len(tasks)
                
                # Check trạng thái từng task
                for task in tasks:
                    current_states[task.id] = (task.status, task.success_count, task.failed_count)
                    
                    if task.id in last_states:
                        if last_states[task.id] != current_states[task.id]:
                            has_changes = True
                    else:
                        has_changes = True
                
                # Nếu có thay đổi, gửi data
                if has_changes:
                    last_states = current_states.copy()
                    
                    # Build response
                    tasks_data = []
                    for task in tasks:
                        # Lấy details cho mỗi task
                        details = session.query(TaskDetail).filter(TaskDetail.task_id == task.id).all()
                        
                        detail_items = []
                        for d in details:
                            # Lấy email từ bảng Account
                            account = session.query(Account).filter(Account.account_code == d.account_code).first()
                            email = account.email if account else None
                            
                            detail_items.append({
                                "id": d.id,
                                "account_code": d.account_code,
                                "email": email,
                                "balance": d.balance,
                                "status": d.status.value if hasattr(d.status, 'value') else d.status,
                                "result_message": d.result_message,
                                "screenshot_path": d.screenshot_path
                            })
                        
                        tasks_data.append({
                            "id": task.id,
                            "task_code": task.task_code,
                            "status": task.status.value if hasattr(task.status, 'value') else task.status,
                            "total_accounts": task.total_accounts,
                            "success_count": task.success_count,
                            "failed_count": task.failed_count,
                            "pending_count": task.total_accounts - task.success_count - task.failed_count,
                            "total_balance": task.total_balance,
                            "progress": round((task.success_count + task.failed_count) / max(task.total_accounts, 1) * 100, 1),
                            "created_at": task.created_at.isoformat() if task.created_at else None,
                            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
                            "details": detail_items
                        })
                    
                    data = {
                        "event": event_type,
                        "timestamp": datetime.utcnow().isoformat(),
                        "total_tasks": len(tasks_data),
                        "tasks": tasks_data
                    }
                    
                    yield f"data: {json.dumps(data)}\n\n"
                    
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                    
            finally:
                session.close()
            
            # Đợi 2 giây trước khi check lại
            await asyncio.sleep(2)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

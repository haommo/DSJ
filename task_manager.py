import asyncio
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, Dict, Set
from models import Task, Account, TaskDetail, TaskStatus, ResultStatus
from automation_runner import run_automation_for_account, automation_manager
from database import SessionLocal
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mô tả các step bằng tiếng Việt
STEP_DESCRIPTIONS = {
    "go_to_login": "Truy cập trang đăng nhập",
    "enter_email": "Nhập email",
    "enter_password": "Nhập mật khẩu",
    "click_login": "Nhấn nút đăng nhập",
    "verify_login": "Xác nhận đăng nhập thành công",
    "go_to_transaction": "Truy cập trang giao dịch",
    "click_invited_me": "Nhấn 'invited me'",
    "enter_code_confirm": "Nhập mã và xác nhận",
    "get_balance": "Lấy số dư tài khoản",
}


def get_error_message(result: dict) -> str:
    """Tạo message lỗi chi tiết từ kết quả automation"""
    failed_step = result.get("failed_step")
    error = result.get("error", "Lỗi không xác định")
    
    if failed_step:
        step_desc = STEP_DESCRIPTIONS.get(failed_step, failed_step)
        return f"Lỗi tại bước '{step_desc}': {error}"
    
    return error


class TaskManager:
    """
    Quản lý và chạy các tasks automation
    Với error handling và state management tốt hơn
    """
    
    def __init__(self):
        self.running_tasks: Dict[int, asyncio.Task] = {}  # task_id -> asyncio.Task
        self.cancelled_tasks: Set[int] = set()  # Set of cancelled task IDs
        
    def get_db(self) -> Session:
        """Lấy database session mới"""
        return SessionLocal()
    
    def _update_task_status(self, db: Session, task: Task, status: TaskStatus):
        """Cập nhật trạng thái task an toàn"""
        try:
            task.status = status
            db.commit()
            logger.info(f"Task {task.task_code} status updated to: {status}")
        except Exception as e:
            logger.error(f"Failed to update task status: {e}")
            db.rollback()
    
    def _update_detail_status(
        self, 
        db: Session, 
        detail: TaskDetail, 
        status: ResultStatus,
        result_message: str = None,
        balance: float = None,
        screenshot_path: str = None
    ):
        """Cập nhật trạng thái detail an toàn"""
        try:
            detail.status = status
            if result_message is not None:
                detail.result_message = result_message
            if balance is not None:
                detail.balance = balance
            if screenshot_path is not None:
                detail.screenshot_path = screenshot_path
            db.commit()
        except Exception as e:
            logger.error(f"Failed to update detail status: {e}")
            db.rollback()
    
    def _update_task_counts(self, db: Session, task: Task, success_count: int, failed_count: int, total_balance: float):
        """Cập nhật counts cho task"""
        try:
            task.success_count = success_count
            task.failed_count = failed_count
            task.total_balance = total_balance
            db.commit()
        except Exception as e:
            logger.error(f"Failed to update task counts: {e}")
            db.rollback()

    async def _process_single_account(
        self,
        detail: TaskDetail,
        account: Account,
        task_code: str,
        headless: bool = True
    ) -> dict:
        """
        Xử lý một account đơn lẻ (dùng cho chạy song song)
        Returns: dict với kết quả automation
        """
        try:
            logger.info(f"[START] {account.account_code} ({account.email})")
            
            result = await run_automation_for_account(
                email=account.email,
                password=account.password,
                order_code=task_code,
                account_code=account.account_code,
                headless=headless
            )
            
            logger.info(f"[DONE] {account.account_code} - Success: {result.get('success')}")
            return result
            
        except Exception as e:
            logger.error(f"[ERROR] {account.account_code}: {e}")
            return {
                "success": False,
                "error": f"Exception during processing: {str(e)}"
            }

    async def run_task(self, task_id: int, headless: bool = True):
        """
        Chạy một task với tất cả accounts (2 accounts song song cùng lúc)
        Với comprehensive error handling
        """
        db = self.get_db()
        
        try:
            # Lấy task từ DB
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                logger.error(f"Task {task_id} not found")
                return
            
            # Kiểm tra task đã bị cancel chưa
            if task_id in self.cancelled_tasks:
                logger.info(f"Task {task_id} was cancelled before starting")
                self._update_task_status(db, task, TaskStatus.FAILED)
                return
            
            # Cập nhật trạng thái task -> RUNNING
            self._update_task_status(db, task, TaskStatus.RUNNING)
            
            logger.info(f"=" * 50)
            logger.info(f"Starting task {task.task_code} with {task.total_accounts} accounts")
            logger.info(f"=" * 50)
            
            # Lấy tất cả task details
            details = db.query(TaskDetail).filter(TaskDetail.task_id == task_id).all()
            
            if not details:
                logger.warning(f"No details found for task {task_id}")
                self._update_task_status(db, task, TaskStatus.COMPLETED)
                return
            
            # Counters
            success_count = 0
            failed_count = 0
            total_balance = 0.0
            
            # Batch size - chạy song song 2 accounts cùng lúc
            BATCH_SIZE = 2
            MAX_AUTO_RETRIES = 2  # Số lần retry tự động cho accounts failed
            
            # Track retry count cho từng account
            retry_counts = {}  # {detail_id: retry_count}
            
            # Lọc các accounts cần chạy (PENDING)
            pending_details = []
            for idx, detail in enumerate(details):
                # Skip các account đã SUCCESS
                if detail.status == ResultStatus.SUCCESS:
                    logger.info(f"[{idx + 1}/{len(details)}] Skipping {detail.account_code} - already SUCCESS")
                    success_count += 1
                    if detail.balance:
                        total_balance += detail.balance
                    continue
                
                # Skip các account không phải PENDING
                if detail.status != ResultStatus.PENDING:
                    logger.info(f"[{idx + 1}/{len(details)}] Skipping {detail.account_code} - status is {detail.status}")
                    if detail.status == ResultStatus.FAILED:
                        failed_count += 1
                    continue
                
                pending_details.append(detail)
            
            logger.info(f"Found {len(pending_details)} pending accounts to process")
            
            # Chạy accounts theo batch (2 accounts song song)
            for batch_start in range(0, len(pending_details), BATCH_SIZE):
                # Kiểm tra cancel
                if task_id in self.cancelled_tasks:
                    logger.info(f"Task {task.task_code} cancelled during execution")
                    # Đánh dấu các detail còn lại là failed
                    for detail in pending_details[batch_start:]:
                        if detail.status == ResultStatus.PENDING:
                            self._update_detail_status(
                                db, detail, ResultStatus.FAILED,
                                result_message="Task cancelled"
                            )
                            failed_count += 1
                    break
                
                # Lấy batch hiện tại (tối đa BATCH_SIZE accounts)
                batch_details = pending_details[batch_start:batch_start + BATCH_SIZE]
                
                logger.info(f"")
                logger.info(f"=" * 50)
                logger.info(f"Processing batch {batch_start // BATCH_SIZE + 1}: {len(batch_details)} accounts")
                logger.info(f"=" * 50)
                
                # Tạo tasks cho batch
                tasks_to_run = []
                for detail in batch_details:
                    # Lấy account info
                    account = db.query(Account).filter(
                        Account.account_code == detail.account_code
                    ).first()
                    
                    if not account:
                        logger.error(f"Account {detail.account_code} not found in database")
                        self._update_detail_status(
                            db, detail, ResultStatus.FAILED,
                            result_message="Account not found in database"
                        )
                        failed_count += 1
                        continue
                    
                    logger.info(f"Queuing account: {account.account_code} ({account.email})")
                    
                    # Cập nhật trạng thái -> RUNNING
                    self._update_detail_status(db, detail, ResultStatus.RUNNING)
                    
                    # Tạo coroutine cho account này
                    tasks_to_run.append(
                        self._process_single_account(
                            detail, account, task.task_code, headless
                        )
                    )
                
                # Chạy batch song song
                if tasks_to_run:
                    logger.info(f"Running {len(tasks_to_run)} accounts in parallel...")
                    results = await asyncio.gather(*tasks_to_run, return_exceptions=True)
                    
                    # Xử lý kết quả từ batch
                    for idx, (detail, result) in enumerate(zip(batch_details, results)):
                        account = db.query(Account).filter(
                            Account.account_code == detail.account_code
                        ).first()
                        
                        if not account:
                            continue
                        
                        # Nếu result là exception
                        if isinstance(result, Exception):
                            logger.error(f"✗ Account {account.account_code} failed with exception: {result}")
                            self._update_detail_status(
                                db, detail, ResultStatus.FAILED,
                                result_message=f"Exception: {str(result)}"
                            )
                            failed_count += 1
                        # Nếu result là dict (kết quả automation)
                        elif isinstance(result, dict):
                            if result.get("success"):
                                self._update_detail_status(
                                    db, detail, ResultStatus.SUCCESS,
                                    result_message="Thành công",
                                    balance=result.get("balance"),
                                    screenshot_path=result.get("screenshot")
                                )
                                success_count += 1
                                
                                if result.get("balance"):
                                    total_balance += result["balance"]
                                
                                logger.info(f"✓ Account {account.account_code} completed successfully")
                            else:
                                error_msg = get_error_message(result)
                                self._update_detail_status(
                                    db, detail, ResultStatus.FAILED,
                                    result_message=error_msg,
                                    screenshot_path=result.get("screenshot")
                                )
                                failed_count += 1
                                logger.error(f"✗ Account {account.account_code} failed: {error_msg}")
                        else:
                            logger.error(f"✗ Account {account.account_code} returned unexpected result type")
                            self._update_detail_status(
                                db, detail, ResultStatus.FAILED,
                                result_message="Unexpected result type"
                            )
                            failed_count += 1
                    
                    # Cập nhật task counts sau mỗi batch
                    self._update_task_counts(db, task, success_count, failed_count, total_balance)
                
                # Delay giữa các batches
                if batch_start + BATCH_SIZE < len(pending_details):
                    await asyncio.sleep(2)
            
            # ============== AUTO RETRY FAILED ACCOUNTS ==============
            logger.info(f"")
            logger.info(f"=" * 50)
            logger.info(f"Checking for failed accounts to retry...")
            logger.info(f"=" * 50)
            
            # Retry failed accounts (tối đa MAX_AUTO_RETRIES lần)
            for retry_round in range(MAX_AUTO_RETRIES):
                # Lấy các accounts failed cần retry
                failed_details = db.query(TaskDetail).filter(
                    TaskDetail.task_id == task_id,
                    TaskDetail.status == ResultStatus.FAILED
                ).all()
                
                # Lọc các accounts chưa retry quá giới hạn
                details_to_retry = []
                for detail in failed_details:
                    current_retries = retry_counts.get(detail.id, 0)
                    if current_retries < MAX_AUTO_RETRIES:
                        details_to_retry.append(detail)
                
                if not details_to_retry:
                    logger.info(f"No failed accounts to retry (round {retry_round + 1})")
                    break
                
                logger.info(f"")
                logger.info(f"RETRY ROUND {retry_round + 1}/{MAX_AUTO_RETRIES}")
                logger.info(f"Found {len(details_to_retry)} failed accounts to retry")
                logger.info(f"=" * 50)
                
                # Chạy retry theo batch
                for batch_start in range(0, len(details_to_retry), BATCH_SIZE):
                    # Kiểm tra cancel
                    if task_id in self.cancelled_tasks:
                        logger.info(f"Task cancelled during retry")
                        break
                    
                    batch_details = details_to_retry[batch_start:batch_start + BATCH_SIZE]
                    
                    logger.info(f"Retrying batch: {len(batch_details)} accounts")
                    
                    # Tạo tasks cho batch
                    tasks_to_run = []
                    for detail in batch_details:
                        account = db.query(Account).filter(
                            Account.account_code == detail.account_code
                        ).first()
                        
                        if not account:
                            continue
                        
                        # Tăng retry count
                        retry_counts[detail.id] = retry_counts.get(detail.id, 0) + 1
                        
                        logger.info(f"Retrying {account.account_code} (attempt {retry_counts[detail.id] + 1})")
                        
                        # Reset trạng thái về PENDING trước khi retry
                        detail.status = ResultStatus.PENDING
                        detail.result_message = None
                        db.commit()
                        
                        # Cập nhật trạng thái -> RUNNING
                        self._update_detail_status(db, detail, ResultStatus.RUNNING)
                        
                        # Tạo coroutine
                        tasks_to_run.append(
                            self._process_single_account(
                                detail, account, task.task_code, headless
                            )
                        )
                    
                    # Chạy batch song song
                    if tasks_to_run:
                        results = await asyncio.gather(*tasks_to_run, return_exceptions=True)
                        
                        # Xử lý kết quả
                        for detail, result in zip(batch_details, results):
                            account = db.query(Account).filter(
                                Account.account_code == detail.account_code
                            ).first()
                            
                            if not account:
                                continue
                            
                            if isinstance(result, Exception):
                                logger.error(f"✗ Retry failed for {account.account_code}: {result}")
                                self._update_detail_status(
                                    db, detail, ResultStatus.FAILED,
                                    result_message=f"Retry failed: {str(result)}"
                                )
                            elif isinstance(result, dict):
                                if result.get("success"):
                                    # Retry thành công - cập nhật lại counters
                                    self._update_detail_status(
                                        db, detail, ResultStatus.SUCCESS,
                                        result_message="Thành công (sau retry)",
                                        balance=result.get("balance"),
                                        screenshot_path=result.get("screenshot")
                                    )
                                    # Chuyển từ failed sang success
                                    failed_count -= 1
                                    success_count += 1
                                    
                                    if result.get("balance"):
                                        total_balance += result["balance"]
                                    
                                    logger.info(f"✓ Retry success for {account.account_code}")
                                else:
                                    error_msg = get_error_message(result)
                                    self._update_detail_status(
                                        db, detail, ResultStatus.FAILED,
                                        result_message=f"Retry failed: {error_msg}",
                                        screenshot_path=result.get("screenshot")
                                    )
                                    logger.error(f"✗ Retry failed for {account.account_code}: {error_msg}")
                        
                        # Cập nhật task counts
                        self._update_task_counts(db, task, success_count, failed_count, total_balance)
                    
                    # Delay giữa các retry batches
                    if batch_start + BATCH_SIZE < len(details_to_retry):
                        await asyncio.sleep(2)
            
            # Hoàn thành task
            final_status = TaskStatus.COMPLETED
            if task_id in self.cancelled_tasks:
                final_status = TaskStatus.FAILED
            
            self._update_task_status(db, task, final_status)
            self._update_task_counts(db, task, success_count, failed_count, total_balance)
            
            logger.info(f"")
            logger.info(f"=" * 50)
            logger.info(f"Task {task.task_code} finished: {success_count} success, {failed_count} failed")
            logger.info(f"Total balance: ${total_balance:.2f}")
            logger.info(f"=" * 50)
            
        except asyncio.CancelledError:
            logger.warning(f"Task {task_id} was cancelled")
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                self._update_task_status(db, task, TaskStatus.FAILED)
                
        except Exception as e:
            logger.error(f"Critical error running task {task_id}: {e}")
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                self._update_task_status(db, task, TaskStatus.FAILED)
                
        finally:
            # Cleanup
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]
            if task_id in self.cancelled_tasks:
                self.cancelled_tasks.discard(task_id)
            db.close()

    async def retry_single_detail(self, task_id: int, detail_id: int, headless: bool = True):
        """
        Chạy lại automation cho một account cụ thể trong task
        """
        db = self.get_db()
        
        try:
            # Lấy task và detail
            task = db.query(Task).filter(Task.id == task_id).first()
            detail = db.query(TaskDetail).filter(TaskDetail.id == detail_id).first()
            
            if not task or not detail:
                logger.error(f"Task {task_id} or Detail {detail_id} not found")
                return
            
            # Lấy account info
            account = db.query(Account).filter(
                Account.account_code == detail.account_code
            ).first()
            
            if not account:
                logger.error(f"Account {detail.account_code} not found")
                self._update_detail_status(
                    db, detail, ResultStatus.FAILED,
                    result_message="Account not found"
                )
                return
            
            logger.info(f"Retrying automation for account {account.account_code}")
            
            # Lưu trạng thái cũ
            was_failed = detail.status == ResultStatus.FAILED
            old_balance = detail.balance or 0
            
            # Cập nhật trạng thái -> RUNNING
            self._update_detail_status(db, detail, ResultStatus.RUNNING)
            
            try:
                # Chạy automation
                result = await run_automation_for_account(
                    email=account.email,
                    password=account.password,
                    order_code=task.task_code,
                    account_code=account.account_code,
                    headless=headless
                )
                
                # Xử lý kết quả
                if result["success"]:
                    self._update_detail_status(
                        db, detail, ResultStatus.SUCCESS,
                        result_message=result.get("message", "Thành công"),
                        balance=result.get("balance"),
                        screenshot_path=result.get("screenshot")
                    )
                    
                    # Cập nhật task counts nếu trước đó failed
                    if was_failed:
                        task.success_count += 1
                        task.failed_count = max(0, task.failed_count - 1)
                    
                    # Cập nhật balance
                    new_balance = result.get("balance") or 0
                    task.total_balance = task.total_balance - old_balance + new_balance
                    db.commit()
                    
                    logger.info(f"✓ Retry successful for {account.account_code}")
                else:
                    error_msg = result.get("error", "Unknown error")
                    self._update_detail_status(
                        db, detail, ResultStatus.FAILED,
                        result_message=error_msg,
                        screenshot_path=result.get("screenshot")
                    )
                    logger.error(f"✗ Retry failed for {account.account_code}: {error_msg}")
                    
            except Exception as e:
                logger.error(f"Error retrying automation for {account.account_code}: {e}")
                self._update_detail_status(
                    db, detail, ResultStatus.FAILED,
                    result_message=str(e)
                )
                
        except Exception as e:
            logger.error(f"Critical error in retry_single_detail: {e}")
        finally:
            db.close()

    def cancel_task(self, task_id: int) -> bool:
        """
        Hủy task đang chạy
        """
        logger.info(f"Cancelling task {task_id}")
        
        # Đánh dấu task cần cancel
        self.cancelled_tasks.add(task_id)
        
        # Cancel asyncio task nếu có
        if task_id in self.running_tasks:
            self.running_tasks[task_id].cancel()
            return True
        
        # Cập nhật DB
        db = self.get_db()
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if task and task.status == TaskStatus.RUNNING:
                task.status = TaskStatus.FAILED
                db.commit()
                return True
        finally:
            db.close()
        
        return False
    
    def is_task_cancelled(self, task_id: int) -> bool:
        """Kiểm tra task có bị cancel không"""
        return task_id in self.cancelled_tasks
    
    def get_running_tasks(self) -> list:
        """Lấy danh sách task đang chạy"""
        return list(self.running_tasks.keys())


# Singleton instance
task_manager = TaskManager()

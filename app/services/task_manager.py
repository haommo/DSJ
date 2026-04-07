"""Task lifecycle management: run, cancel, retry."""

import asyncio
import logging
from typing import Dict, Set
from sqlalchemy.orm import Session

from app.models.task import Task, TaskDetail, TaskStatus, ResultStatus, TaskType
from app.models.account import Account
from app.automation.runner import run_automation_for_account, run_follow_order_for_account
from app.database import SessionLocal
from app.services.setting_service import get_setting
from app.services.crypto_service import decrypt_password, is_encrypted
from app.services.task_result_handler import safe_commit, get_error_message
from app.services.task_executor import execute_task

logger = logging.getLogger(__name__)


class TaskManager:
    def __init__(self):
        self.running_tasks: Dict[int, asyncio.Task] = {}
        self.cancelled_tasks: Set[int] = set()

    def get_db(self) -> Session:
        return SessionLocal()

    async def run_task(self, task_id: int, headless: bool = True):
        db = self.get_db()
        try:
            await execute_task(task_id, db, self.cancelled_tasks, headless)
        except asyncio.CancelledError:
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                safe_commit(db, task, status=TaskStatus.FAILED)
        except Exception as e:
            logger.error(f"Critical error task {task_id}: {e}")
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                safe_commit(db, task, status=TaskStatus.FAILED)
        finally:
            self.running_tasks.pop(task_id, None)
            self.cancelled_tasks.discard(task_id)
            db.close()

    async def retry_single_detail(self, task_id: int, detail_id: int, headless: bool = True):
        db = self.get_db()
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            detail = db.query(TaskDetail).filter(TaskDetail.id == detail_id).first()
            if not task or not detail:
                return

            account = db.query(Account).filter(
                Account.account_code == detail.account_code).first()
            if not account:
                safe_commit(db, detail, status=ResultStatus.FAILED,
                            result_message="Account not found")
                return

            was_failed = detail.status == ResultStatus.FAILED
            old_balance = detail.balance or 0
            safe_commit(db, detail, status=ResultStatus.RUNNING)

            site_domain = get_setting(db, "site_domain")
            bg_signal_text = get_setting(db, "bg_signal_text")
            password = decrypt_password(account.password) if is_encrypted(account.password) else account.password

            if task.task_type == TaskType.MISSION:
                result = await run_follow_order_for_account(
                    email=account.email, password=password,
                    account_code=account.account_code,
                    headless=headless, site_domain=site_domain,
                    bg_signal_text=bg_signal_text,
                    confirm_text=get_setting(db, "follow_confirm_text"),
                    done_text=get_setting(db, "follow_done_text"),
                    completed_text=get_setting(db, "follow_completed_text"),
                    task_id=task_id,
                )
            else:
                result = await run_automation_for_account(
                    email=account.email, password=password,
                    order_code=task.task_code, account_code=account.account_code,
                    headless=headless, site_domain=site_domain,
                    bg_signal_text=bg_signal_text,
                )

            if result.get("success"):
                safe_commit(db, detail, status=ResultStatus.SUCCESS,
                            result_message="Thành công",
                            balance=result.get("balance"),
                            screenshot_path=result.get("screenshot"))
                if was_failed:
                    task.success_count += 1
                    task.failed_count = max(0, task.failed_count - 1)
                new_bal = result.get("balance") or 0
                task.total_balance = task.total_balance - old_balance + new_bal
                db.commit()
            else:
                safe_commit(db, detail, status=ResultStatus.FAILED,
                            result_message=get_error_message(result),
                            screenshot_path=result.get("screenshot"))
        except Exception as e:
            logger.error(f"Error retry detail {detail_id}: {e}")
        finally:
            db.close()

    def cancel_task(self, task_id: int) -> bool:
        self.cancelled_tasks.add(task_id)
        if task_id in self.running_tasks:
            self.running_tasks[task_id].cancel()
            return True
        db = self.get_db()
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if task and task.status == TaskStatus.RUNNING:
                safe_commit(db, task, status=TaskStatus.FAILED)
                return True
        finally:
            db.close()
        return False


task_manager = TaskManager()

"""Batch processing and retry loop for task execution."""

import asyncio
import logging
from sqlalchemy.orm import Session

from app.models.task import Task, TaskDetail, TaskStatus, ResultStatus, TaskType
from app.models.account import Account
from app.automation.runner import run_automation_for_account, run_follow_order_for_account
from app.services.setting_service import get_setting, get_setting_int
from app.services.crypto_service import decrypt_password, is_encrypted
from app.services.task_result_handler import safe_commit, handle_result

logger = logging.getLogger(__name__)

MAX_RETRY_DURATION = 1800  # 30 minutes


async def _process_account(
    detail, account, task_code, headless=True, site_domain: str = "",
    task_type="task", confirm_text="", done_text="", completed_text="",
    task_id=0, bg_signal_text: str = "",
) -> dict:
    try:
        password = decrypt_password(account.password) if is_encrypted(account.password) else account.password
        if task_type == TaskType.MISSION:
            return await run_follow_order_for_account(
                email=account.email, password=password,
                account_code=account.account_code,
                headless=headless, site_domain=site_domain,
                bg_signal_text=bg_signal_text,
                confirm_text=confirm_text, done_text=done_text,
                completed_text=completed_text,
                task_id=task_id,
            )
        return await run_automation_for_account(
            email=account.email, password=password,
            order_code=task_code, account_code=account.account_code,
            headless=headless, site_domain=site_domain,
            bg_signal_text=bg_signal_text,
        )
    except Exception as e:
        return {"success": False, "error": f"Exception: {str(e)}"}


async def execute_task(task_id: int, db: Session, cancelled_tasks: set, headless: bool = True):
    """Run pending details in batches, then auto-retry failed ones."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return

    if task_id in cancelled_tasks:
        safe_commit(db, task, status=TaskStatus.FAILED)
        return

    safe_commit(db, task, status=TaskStatus.RUNNING)
    details = db.query(TaskDetail).filter(TaskDetail.task_id == task_id).all()

    counters = {"success": 0, "failed": 0, "balance": 0.0}

    BATCH_SIZE = get_setting_int(db, "batch_size")
    MAX_AUTO_RETRIES = get_setting_int(db, "max_retries")
    SITE_DOMAIN = get_setting(db, "site_domain")
    BG_SIGNAL_TEXT = get_setting(db, "bg_signal_text")

    # Follow-order settings (only used for missions)
    follow_kwargs = {}
    if task.task_type == TaskType.MISSION:
        follow_kwargs = {
            "task_type": TaskType.MISSION,
            "task_id": task_id,
            "confirm_text": get_setting(db, "follow_confirm_text"),
            "done_text": get_setting(db, "follow_done_text"),
            "completed_text": get_setting(db, "follow_completed_text"),
        }

    # Classify existing results
    pending_details = []
    for d in details:
        if d.status == ResultStatus.SUCCESS:
            counters["success"] += 1
            counters["balance"] += d.balance or 0
        elif d.status == ResultStatus.FAILED:
            counters["failed"] += 1
        elif d.status == ResultStatus.PENDING:
            pending_details.append(d)

    # Pre-fetch accounts (avoid N+1)
    all_codes = list({d.account_code for d in pending_details})
    all_accounts = db.query(Account).filter(Account.account_code.in_(all_codes)).all() if all_codes else []
    accounts_map = {a.account_code: a for a in all_accounts}

    # Process pending in batches
    for i in range(0, len(pending_details), BATCH_SIZE):
        if task_id in cancelled_tasks:
            for d in pending_details[i:]:
                if d.status == ResultStatus.PENDING:
                    safe_commit(db, d, status=ResultStatus.FAILED, result_message="Task cancelled")
                    counters["failed"] += 1
            break

        batch = pending_details[i:i + BATCH_SIZE]
        tasks_to_run = []
        valid_details = []

        for d in batch:
            account = accounts_map.get(d.account_code)
            if not account:
                safe_commit(db, d, status=ResultStatus.FAILED, result_message="Account not found")
                counters["failed"] += 1
                continue
            safe_commit(db, d, status=ResultStatus.RUNNING)
            valid_details.append(d)
            tasks_to_run.append(
                _process_account(d, account, task.task_code, headless, site_domain=SITE_DOMAIN, bg_signal_text=BG_SIGNAL_TEXT, **follow_kwargs)
            )

        if tasks_to_run:
            results = await asyncio.gather(*tasks_to_run, return_exceptions=True)
            for d, r in zip(valid_details, results):
                handle_result(db, d, r, counters)

            safe_commit(db, task,
                        success_count=counters["success"],
                        failed_count=counters["failed"],
                        total_balance=counters["balance"])

        if i + BATCH_SIZE < len(pending_details):
            await asyncio.sleep(2)

    # Auto retry failed details
    retry_start = asyncio.get_event_loop().time()
    for _ in range(MAX_AUTO_RETRIES):
        if asyncio.get_event_loop().time() - retry_start > MAX_RETRY_DURATION:
            logger.warning(f"Task {task_id}: auto-retry timeout reached")
            break

        failed = db.query(TaskDetail).filter(
            TaskDetail.task_id == task_id,
            TaskDetail.status == ResultStatus.FAILED,
        ).all()
        if not failed or task_id in cancelled_tasks:
            break

        retry_codes = list({d.account_code for d in failed})
        retry_accounts = db.query(Account).filter(Account.account_code.in_(retry_codes)).all()
        retry_map = {a.account_code: a for a in retry_accounts}

        for i in range(0, len(failed), BATCH_SIZE):
            batch = failed[i:i + BATCH_SIZE]
            runs = []
            valid = []
            for d in batch:
                acc = retry_map.get(d.account_code)
                if not acc:
                    continue
                safe_commit(db, d, status=ResultStatus.RUNNING, result_message=None)
                valid.append(d)
                runs.append(_process_account(d, acc, task.task_code, headless, site_domain=SITE_DOMAIN, bg_signal_text=BG_SIGNAL_TEXT, **follow_kwargs))

            if runs:
                # All items in retry batch were previously FAILED
                results = await asyncio.gather(*runs, return_exceptions=True)
                for d, r in zip(valid, results):
                    old_success = counters["success"]
                    handle_result(db, d, r, counters)
                    # If retry succeeded, subtract from failed count
                    if counters["success"] > old_success:
                        counters["failed"] = max(0, counters["failed"] - 1)

                safe_commit(db, task,
                            success_count=counters["success"],
                            failed_count=counters["failed"],
                            total_balance=counters["balance"])

    # Final status
    final = TaskStatus.COMPLETED if task_id not in cancelled_tasks else TaskStatus.FAILED
    safe_commit(db, task, status=final,
                success_count=counters["success"],
                failed_count=counters["failed"],
                total_balance=counters["balance"])

"""Handle automation results and error message formatting."""

import logging
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

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
    failed_step = result.get("failed_step")
    error = result.get("error", "Lỗi không xác định")
    if failed_step:
        step_desc = STEP_DESCRIPTIONS.get(failed_step, failed_step)
        return f"Lỗi tại bước '{step_desc}': {error}"
    return error


def safe_commit(db: Session, obj, **kwargs):
    """Safely update object attributes and commit."""
    try:
        for k, v in kwargs.items():
            setattr(obj, k, v)
        db.commit()
    except Exception as e:
        logger.error(f"DB commit failed: {e}")
        db.rollback()


def handle_result(db: Session, detail, result, counters: dict):
    """Process automation result, update detail status and counters in-place."""
    from app.models.task import ResultStatus

    if isinstance(result, Exception):
        safe_commit(db, detail, status=ResultStatus.FAILED,
                    result_message=f"Exception: {str(result)}")
        counters["failed"] += 1
    elif isinstance(result, dict):
        if result.get("success"):
            safe_commit(db, detail, status=ResultStatus.SUCCESS,
                        result_message="Thành công",
                        balance=result.get("balance"),
                        screenshot_path=result.get("screenshot"))
            counters["success"] += 1
            counters["balance"] += result.get("balance") or 0
        else:
            msg = get_error_message(result)
            safe_commit(db, detail, status=ResultStatus.FAILED,
                        result_message=msg,
                        screenshot_path=result.get("screenshot"))
            counters["failed"] += 1
    else:
        safe_commit(db, detail, status=ResultStatus.FAILED,
                    result_message="Unexpected result type")
        counters["failed"] += 1

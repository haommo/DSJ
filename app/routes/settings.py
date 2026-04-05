from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.user import User, UserRole
from app.models.system_setting import SystemSetting
from app.schemas.system_setting import SettingUpdate, SettingResponse, AutomationSettingsResponse, FollowSettingsResponse
from app.services.setting_service import get_setting, get_setting_int, DEFAULTS, invalidate_cache
from app.dependencies import require_roles

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("", response_model=List[SettingResponse])
def get_all_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Lấy tất cả settings (Admin only)"""
    rows = db.query(SystemSetting).all()
    existing_keys = {r.key for r in rows}

    result = list(rows)
    for key, (value, desc) in DEFAULTS.items():
        if key not in existing_keys:
            result.append(SystemSetting(key=key, value=value, description=desc))
    return result


@router.get("/automation", response_model=AutomationSettingsResponse)
def get_automation_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.STAFF)),
):
    """Lấy settings automation dạng gọn (Admin/Staff)"""
    return AutomationSettingsResponse(
        batch_size=get_setting_int(db, "batch_size"),
        max_retries=get_setting_int(db, "max_retries"),
        site_domain=get_setting(db, "site_domain"),
        bg_signal_text=get_setting(db, "bg_signal_text"),
    )


@router.get("/follow", response_model=FollowSettingsResponse)
def get_follow_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Lấy settings follow order (Admin only)"""
    return FollowSettingsResponse(
        follow_confirm_text=get_setting(db, "follow_confirm_text"),
        follow_done_text=get_setting(db, "follow_done_text"),
        follow_completed_text=get_setting(db, "follow_completed_text"),
    )


@router.put("/{key}", response_model=SettingResponse)
def update_setting(
    key: str,
    data: SettingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Cập nhật một setting (Admin only)"""
    if key not in DEFAULTS:
        raise HTTPException(status_code=400, detail=f"Unknown setting key: {key}")

    # Validate int fields
    if key in ("batch_size", "max_retries"):
        try:
            val = int(data.value)
            if val < 1:
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=400, detail=f"{key} phải là số nguyên >= 1")

    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if row:
        row.value = data.value
    else:
        _, desc = DEFAULTS[key]
        row = SystemSetting(key=key, value=data.value, description=desc)
        db.add(row)

    db.commit()
    db.refresh(row)
    invalidate_cache(key)
    return row

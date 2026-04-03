from __future__ import annotations

import time
from typing import Optional
from sqlalchemy.orm import Session
from app.models.system_setting import SystemSetting

# Default values - used when no DB row exists
DEFAULTS = {
    "batch_size": ("2", "Số account chạy đồng thời trong 1 batch"),
    "max_retries": ("2", "Số lần retry tự động cho account thất bại"),
    "site_domain": ("dsj079.com", "Domain website DSJ để chạy automation"),
}

# In-memory cache: {key: (value, timestamp)}
_cache: dict[str, tuple[str, float]] = {}
_CACHE_TTL = 30  # seconds


def _cache_get(key: str) -> Optional[str]:
    if key in _cache:
        val, ts = _cache[key]
        if time.time() - ts < _CACHE_TTL:
            return val
        del _cache[key]
    return None


def _cache_set(key: str, value: str):
    _cache[key] = (value, time.time())


def invalidate_cache(key: str = None):
    """Xóa cache khi setting thay đổi"""
    if key:
        _cache.pop(key, None)
    else:
        _cache.clear()


def get_setting(db: Session, key: str) -> str:
    """Lấy giá trị setting từ cache/DB, trả về default nếu chưa có"""
    cached = _cache_get(key)
    if cached is not None:
        return cached

    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if row:
        _cache_set(key, row.value)
        return row.value
    default_val, _ = DEFAULTS.get(key, ("", ""))
    _cache_set(key, default_val)
    return default_val


def get_setting_int(db: Session, key: str) -> int:
    """Lấy setting dạng int"""
    return int(get_setting(db, key))


def seed_defaults(db: Session):
    """Tạo các settings mặc định nếu chưa có"""
    for key, (value, description) in DEFAULTS.items():
        existing = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if not existing:
            db.add(SystemSetting(key=key, value=value, description=description))
    db.commit()

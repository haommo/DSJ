import base64
import logging
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


def _get_key() -> str:
    from app.config import settings
    return settings.ACCOUNT_ENCRYPTION_KEY


def _get_fernet() -> Fernet:
    key = _get_key()
    if not key:
        raise RuntimeError(
            "ACCOUNT_ENCRYPTION_KEY is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode())


def encrypt_password(plain: str) -> str:
    """Encrypt account password for DB storage (reversible)."""
    f = _get_fernet()
    return f.encrypt(plain.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    """Decrypt account password from DB."""
    f = _get_fernet()
    return f.decrypt(encrypted.encode()).decode()


def is_encrypted(value: str) -> bool:
    """Check if a value looks like a Fernet token (base64, starts with gAAAAA)."""
    try:
        if not value or len(value) < 50:
            return False
        base64.urlsafe_b64decode(value)
        return value.startswith("gAAAAA")
    except Exception:
        return False

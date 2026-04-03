from typing import List

from sqlalchemy.orm import Session
from app.models.account import Account
from app.models.user import User


def get_customer_account_codes(db: Session, user: User) -> List[str]:
    """Lấy danh sách account_code của customer"""
    return [
        a.account_code for a in
        db.query(Account).filter(Account.owner_id == user.id).all()
    ]

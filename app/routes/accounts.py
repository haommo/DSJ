from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.user import User, UserRole
from app.models.account import Account
from app.schemas.account import AccountCreate, AccountUpdate, AccountResponse
from app.dependencies import get_current_user, require_roles
from app.services.crypto_service import encrypt_password, is_encrypted

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.get("", response_model=List[AccountResponse])
def get_accounts(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lấy danh sách tài khoản:
    - Admin/Staff: xem tất cả
    - Customer: chỉ xem accounts của mình
    """
    query = db.query(Account)
    if current_user.role in (UserRole.CUSTOMER, UserRole.STAFF):
        query = query.filter(Account.owner_id == current_user.id)
    return query.offset(skip).limit(limit).all()


@router.get("/{account_id}", response_model=AccountResponse)
def get_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lấy thông tin một tài khoản"""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if current_user.role in (UserRole.CUSTOMER, UserRole.STAFF) and account.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    return account


@router.post("", response_model=AccountResponse)
def create_account(
    account: AccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.STAFF)),
):
    """Thêm tài khoản mới (Admin/Staff)"""
    existing = db.query(Account).filter(Account.account_code == account.account_code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Account code already exists")

    existing_email = db.query(Account).filter(Account.email == account.email).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already exists")

    if account.owner_id:
        owner = db.query(User).filter(User.id == account.owner_id).first()
        if not owner:
            raise HTTPException(status_code=400, detail="Owner user not found")

    account_data = account.model_dump()
    account_data["password"] = encrypt_password(account_data["password"])
    db_account = Account(**account_data)
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account


@router.put("/{account_id}", response_model=AccountResponse)
def update_account(
    account_id: int,
    account: AccountUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.STAFF)),
):
    """Sửa tài khoản (Admin/Staff)"""
    db_account = db.query(Account).filter(Account.id == account_id).first()
    if not db_account:
        raise HTTPException(status_code=404, detail="Account not found")

    update_data = account.model_dump(exclude_unset=True)

    if "account_code" in update_data and update_data["account_code"] != db_account.account_code:
        existing = db.query(Account).filter(Account.account_code == update_data["account_code"]).first()
        if existing:
            raise HTTPException(status_code=400, detail="Account code already exists")

    if "email" in update_data and update_data["email"] != db_account.email:
        existing = db.query(Account).filter(Account.email == update_data["email"]).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already exists")

    if "password" in update_data:
        update_data["password"] = encrypt_password(update_data["password"])
    for key, value in update_data.items():
        setattr(db_account, key, value)

    db.commit()
    db.refresh(db_account)
    return db_account


@router.delete("/{account_id}")
def delete_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.STAFF)),
):
    """Xóa tài khoản (Admin/Staff)"""
    db_account = db.query(Account).filter(Account.id == account_id).first()
    if not db_account:
        raise HTTPException(status_code=404, detail="Account not found")

    db.delete(db_account)
    db.commit()
    return {"message": "Account deleted successfully"}

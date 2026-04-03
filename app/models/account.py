from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Account(Base):
    """Bảng tài khoản DSJ"""
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    account_code = Column(String(50), unique=True, index=True)
    email = Column(String(255), unique=True, index=True)
    password = Column(String(255))
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    owner = relationship("User", backref="accounts")

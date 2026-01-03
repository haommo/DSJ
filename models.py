from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ResultStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class Account(Base):
    """Table 1: Account"""
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    account_code = Column(String(50), unique=True, index=True)  # Mã tài khoản DSJ (VD: AQPS7UO3IG00)
    email = Column(String(255), unique=True, index=True)
    password = Column(String(255))


class Task(Base):
    """Table 2: Task"""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_code = Column(String(50), unique=True, index=True)  # Mã nhiệm vụ (VD: 1BTEQ6KHU)
    status = Column(String(20), default=TaskStatus.PENDING)
    total_accounts = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    total_balance = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship
    details = relationship("TaskDetail", back_populates="task")


class TaskDetail(Base):
    """Table 3: Task Detail"""
    __tablename__ = "task_details"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"))
    account_code = Column(String(50))  # Mã tài khoản DSJ
    balance = Column(Float, nullable=True)
    status = Column(String(20), default=ResultStatus.PENDING)
    result_message = Column(Text, nullable=True)
    screenshot_path = Column(String(500), nullable=True)

    # Relationship
    task = relationship("Task", back_populates="details")

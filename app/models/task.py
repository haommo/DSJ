from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float, Text, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ResultStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class TaskType(str, enum.Enum):
    TASK = "task"
    MISSION = "mission"


class Task(Base):
    """Bảng nhiệm vụ automation"""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_code = Column(String(50), unique=True, index=True)
    task_type = Column(String(20), default=TaskType.TASK, nullable=False)
    status = Column(String(20), default=TaskStatus.PENDING)
    total_accounts = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    total_balance = Column(Float, default=0.0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    headless = Column(Boolean, default=True, nullable=False)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    details = relationship("TaskDetail", back_populates="task")
    creator = relationship("User", backref="tasks")


class TaskDetail(Base):
    """Bảng chi tiết kết quả từng account trong task"""
    __tablename__ = "task_details"
    __table_args__ = (
        Index("ix_task_details_task_status", "task_id", "status"),
        Index("ix_task_details_task_account", "task_id", "account_code"),
    )

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"))
    account_code = Column(String(50))
    balance = Column(Float, nullable=True)
    status = Column(String(20), default=ResultStatus.PENDING)
    result_message = Column(Text, nullable=True)
    screenshot_path = Column(String(500), nullable=True)

    task = relationship("Task", back_populates="details")

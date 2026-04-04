"""Background scheduler: checks for scheduled missions and runs them when due."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from app.database import SessionLocal
from app.models.task import Task, TaskStatus, TaskType

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 30  # seconds


async def mission_scheduler():
    """Periodically check for scheduled missions that are due and trigger them."""
    while True:
        try:
            await _check_scheduled_missions()
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)


async def _check_scheduled_missions():
    db = SessionLocal()
    try:
        vn_tz = timezone(timedelta(hours=7))
        now = datetime.now(vn_tz)
        due_missions = db.query(Task).filter(
            Task.task_type == TaskType.MISSION,
            Task.status == TaskStatus.SCHEDULED,
            Task.scheduled_at <= now,
        ).all()

        if not due_missions:
            return

        from app.services.task_manager import task_manager

        for mission in due_missions:
            mission.status = TaskStatus.PENDING
            db.commit()
            logger.info(f"Scheduler: triggering mission {mission.task_code} (scheduled_at={mission.scheduled_at})")
            asyncio.create_task(task_manager.run_task(mission.id, mission.headless))

    except Exception as e:
        logger.error(f"Scheduler check error: {e}")
        db.rollback()
    finally:
        db.close()

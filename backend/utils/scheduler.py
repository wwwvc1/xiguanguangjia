"""
定时任务调度
- 每周日 20:00 给所有用户生成周报
- 每月最后一天 22:00 生成月报
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from database import get_connection
from utils.report_generator import generate_weekly_report, generate_monthly_report
import logging

log = logging.getLogger(__name__)

_scheduler = None


def _all_user_ids() -> list:
    conn = get_connection()
    ids = []
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users")
            ids = [row["id"] for row in cursor.fetchall()]
    finally:
        conn.close()
    return ids


def _run_weekly():
    log.info("[Scheduler] 开始生成所有用户周报")
    for uid in _all_user_ids():
        try:
            r = generate_weekly_report(uid)
            log.info(f"[Scheduler] user {uid} 周报生成: {r.get('period')}")
        except Exception as e:
            log.exception(f"[Scheduler] user {uid} 周报失败: {e}")


def _run_monthly():
    log.info("[Scheduler] 开始生成所有用户月报")
    for uid in _all_user_ids():
        try:
            r = generate_monthly_report(uid)
            log.info(f"[Scheduler] user {uid} 月报生成: {r.get('period')}")
        except Exception as e:
            log.exception(f"[Scheduler] user {uid} 月报失败: {e}")


def start_scheduler():
    """在 FastAPI 启动时调用"""
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    # 每周日 20:00
    _scheduler.add_job(_run_weekly, CronTrigger(day_of_week="sun", hour=20, minute=0), id="weekly_report")
    # 每月最后一天 22:00
    _scheduler.add_job(_run_monthly, CronTrigger(day="last", hour=22, minute=0), id="monthly_report")
    _scheduler.start()
    log.info("[Scheduler] 启动完成,周报每周日 20:00,月报每月最后一天 22:00")


def stop_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None

from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.scheduler import scheduler, setup_scheduler


def test_setup_scheduler_runs_weekly_on_sunday_afternoon(monkeypatch):
    monkeypatch.setattr(settings, "SYNC_ENABLED", True)
    monkeypatch.setattr(settings, "SYNC_DAY_OF_WEEK", "sun")
    monkeypatch.setattr(settings, "SYNC_HOUR", 17)
    monkeypatch.setattr(settings, "SYNC_MINUTE", 0)
    monkeypatch.setattr(settings, "SYNC_TIMEZONE", "Asia/Jakarta")

    scheduler.remove_all_jobs()
    try:
        setup_scheduler()
        setup_scheduler()
        jobs = scheduler.get_jobs()

        assert len(jobs) == 1
        job = jobs[0]
        assert isinstance(job.trigger, CronTrigger)
        assert job.coalesce is True
        assert job.max_instances == 1
        assert job.misfire_grace_time == 3600

        fields = {
            name: str(field)
            for name, field in zip(job.trigger.FIELD_NAMES, job.trigger.fields)
        }
        assert fields["day_of_week"] == "sun"
        assert fields["hour"] == "17"
        assert fields["minute"] == "0"
        assert str(job.trigger.timezone) == "Asia/Jakarta"

        after = datetime(2026, 8, 20, 12, 0, tzinfo=ZoneInfo("Asia/Jakarta"))
        next_run = job.trigger.get_next_fire_time(None, after)
        assert next_run == datetime(2026, 8, 23, 17, 0, tzinfo=ZoneInfo("Asia/Jakarta"))
    finally:
        scheduler.remove_all_jobs()


def test_disabled_scheduler_has_no_job(monkeypatch):
    monkeypatch.setattr(settings, "SYNC_ENABLED", False)
    scheduler.remove_all_jobs()

    setup_scheduler()

    assert scheduler.get_job("batch_sync_job") is None

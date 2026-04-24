import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.clustering import run_clustering
from app.config import settings
from app.db import get_session
from app.ingestion import fetch_new_posts
from app.models import IngestionRun
from app.scoring import score_cluster

log = logging.getLogger(__name__)

INGESTION_PIPELINE_JOB_ID = "ingestion_pipeline"
STALE_DATA_CHECK_JOB_ID = "stale_data_check"

scheduler = AsyncIOScheduler(timezone="UTC")


async def run_ingestion_pipeline_job() -> None:
    """Fetch new posts, cluster them, then score each resulting cluster."""
    try:
        new_posts = await fetch_new_posts()
        if not new_posts:
            log.info("Scheduler pipeline: no new posts fetched")
            return

        clusters = await run_clustering(new_posts)
        if not clusters:
            log.info("Scheduler pipeline: no clusters created from %d new posts", len(new_posts))
            return

        scored = 0
        for cluster in clusters:
            await score_cluster(cluster.id)
            scored += 1

        log.info(
            "Scheduler pipeline complete: %d posts -> %d clusters scored",
            len(new_posts),
            scored,
        )
    except Exception:
        log.exception("Scheduler pipeline failed")


async def run_stale_data_check_job() -> None:
    """Emit a stale-data alert if the latest ingestion run is older than threshold."""
    now = datetime.now(timezone.utc)

    try:
        async with get_session() as db:
            latest_run = (
                await db.execute(select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(1))
            ).scalar_one_or_none()
    except Exception:
        log.exception("STALE_DATA_ALERT_CHECK_FAILED: unable to query ingestion_runs")
        return

    if latest_run is None:
        log.warning(
            "STALE_DATA_ALERT: no ingestion runs found (threshold=%d minutes)",
            settings.stale_data_threshold_minutes,
        )
        return

    reference_time = latest_run.completed_at or latest_run.started_at
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)

    age_minutes = (now - reference_time).total_seconds() / 60
    if age_minutes > settings.stale_data_threshold_minutes:
        log.warning(
            "STALE_DATA_ALERT: latest ingestion is %.1f minutes old (threshold=%d, run_id=%s, status=%s)",
            age_minutes,
            settings.stale_data_threshold_minutes,
            latest_run.id,
            latest_run.status,
        )


def start_scheduler() -> None:
    if scheduler.running:
        return

    scheduler.add_job(
        run_ingestion_pipeline_job,
        trigger=IntervalTrigger(seconds=settings.ingestion_interval_seconds),
        id=INGESTION_PIPELINE_JOB_ID,
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )

    scheduler.add_job(
        run_stale_data_check_job,
        trigger=IntervalTrigger(minutes=5),
        id=STALE_DATA_CHECK_JOB_ID,
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )

    scheduler.start()
    log.info(
        "Scheduler started (ingestion_interval=%ss, stale_threshold=%sm)",
        settings.ingestion_interval_seconds,
        settings.stale_data_threshold_minutes,
    )


def stop_scheduler() -> None:
    if not scheduler.running:
        return
    scheduler.shutdown(wait=False)
    log.info("Scheduler stopped")

"""
Mr.Creative — Auto Scheduler Engine
Uses APScheduler to check for due jobs every 60 seconds.
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
import threading
import json

_scheduler = None
_scheduler_lock = threading.Lock()


def init_scheduler(app):
    global _scheduler
    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        func=_check_due_jobs,
        trigger=IntervalTrigger(seconds=60),
        id='check_due_jobs',
        name='Check for scheduled Pomelli jobs',
        replace_existing=True,
        kwargs={'app': app},
    )
    _scheduler.start()
    print("[AutoScheduler] Started — checking for due jobs every 60s")

    import atexit
    atexit.register(lambda: _shutdown_scheduler())


def _shutdown_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        print("[AutoScheduler] Shut down")
        _scheduler = None


def _check_due_jobs(app):
    with app.app_context():
        from models import db, ScheduledJob

        now = datetime.now()

        active_count = ScheduledJob.query.filter(
            ScheduledJob.is_active == True,
            ScheduledJob.next_run != None,
        ).count()
        if active_count > 0:
            print(f"[AutoScheduler] Checking... now={now.strftime('%H:%M:%S')}, {active_count} active job(s)")

        due_jobs = ScheduledJob.query.filter(
            ScheduledJob.is_active == True,
            ScheduledJob.next_run != None,
            ScheduledJob.next_run <= now,
        ).all()

        if not due_jobs:
            return

        print(f"[AutoScheduler] Found {len(due_jobs)} due job(s)")

        for job in due_jobs:
            try:
                _execute_scheduled_job(app, job, now)
            except Exception as e:
                print(f"[AutoScheduler] Error executing job '{job.name}': {e}")


def _execute_scheduled_job(app, job, now):
    from models import db, ScheduledJob, JobQueue, Collection
    from routes.generate import (
        update_bot_status, run_bot_in_background, run_photoshoot_in_background
    )

    print(f"[AutoScheduler] Executing: '{job.name}' (feature={job.pomelli_feature})")

    timestamp = now.strftime('%b %d %H:%M')
    col_name = f"{job.name} — {timestamp}"
    collection = Collection(
        user_id=job.user_id,
        name=col_name[:200],
        description=f'Auto-scheduled: {job.name} ({job.pomelli_feature}, {job.schedule_type})'
    )
    db.session.add(collection)
    db.session.flush()

    queue_job = JobQueue(
        user_id=job.user_id,
        job_type='generate' if job.pomelli_feature == 'campaign' else 'photoshoot',
        status='queued',
    )
    db.session.add(queue_job)

    job.last_run = now
    if job.schedule_type == 'once':
        job.is_active = False
        job.next_run = None
    elif job.schedule_type == 'daily':
        next_run = job.next_run + timedelta(days=1)
        while next_run <= now:
            next_run += timedelta(days=1)
        job.next_run = next_run
    elif job.schedule_type == 'weekly':
        next_run = job.next_run + timedelta(weeks=1)
        while next_run <= now:
            next_run += timedelta(weeks=1)
        job.next_run = next_run

    db.session.commit()

    try:
        templates = json.loads(job.templates) if job.templates else []
    except (json.JSONDecodeError, TypeError):
        templates = []

    update_bot_status(queue_job.id, 'queued', f'Auto-scheduled: {job.name}', 0)

    if job.pomelli_feature == 'photoshoot':
        if not job.image_path:
            print(f"[AutoScheduler] ERROR: Photoshoot job '{job.name}' has no image — skipping")
            queue_job.status = 'failed'
            queue_job.error_message = 'No product image configured'
            db.session.commit()
            return

        thread = threading.Thread(
            target=run_photoshoot_in_background,
            args=(app, job.image_path, templates, 'product',
                  collection.id, job.user_id, queue_job.id,
                  job.prompt_text or '', job.aspect_ratio or 'story'),
            daemon=True
        )
    elif job.pomelli_feature == 'generate':
        thread = threading.Thread(
            target=run_photoshoot_in_background,
            args=(app, job.image_path, [], 'generate',
                  collection.id, job.user_id, queue_job.id,
                  job.prompt_text or '', job.aspect_ratio or 'story'),
            daemon=True
        )
    else:
        # Campaign — text prompt with optional product_url, image, aspect_ratio
        thread = threading.Thread(
            target=run_bot_in_background,
            args=(app, job.prompt_text, collection.id, job.user_id, queue_job.id,
                  False, job.product_url or '', job.aspect_ratio, job.image_path),
            daemon=True
        )

    thread.start()
    print(f"[AutoScheduler] Launched '{job.name}' -> job_id={queue_job.id}, collection_id={collection.id}")

    if job.next_run:
        print(f"[AutoScheduler] Next run for '{job.name}': {job.next_run.strftime('%Y-%m-%d %H:%M')}")
    else:
        print(f"[AutoScheduler] '{job.name}' is now inactive (one-time job)")


def get_scheduler_status():
    global _scheduler
    if _scheduler and _scheduler.running:
        jobs = _scheduler.get_jobs()
        return {
            'running': True,
            'job_count': len(jobs),
            'next_check': str(jobs[0].next_run_time) if jobs else None,
        }
    return {'running': False}
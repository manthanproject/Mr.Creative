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

        # ── Check due social posts ──
        try:
            _post_due_social(app)
        except Exception as e:
            print(f"[AutoScheduler] Social post error: {e}")

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


def _post_due_social(app):
    """Post any social posts that are due."""
    with app.app_context():
        from models import SocialPost, db
        from datetime import datetime

        due_posts = SocialPost.query.filter(
            SocialPost.status == 'scheduled',
            SocialPost.scheduled_at <= datetime.now()
        ).all()

        if not due_posts:
            return

        token = app.config.get('PINTEREST_ACCESS_TOKEN', '')
        if not token:
            print("[AutoScheduler] No Pinterest token — skipping social posts")
            return

        from modules.pinterest_api import PinterestAPI
        import os
        api = PinterestAPI(token)

        for post in due_posts:
            try:
                if not post.board_id:
                    post.status = 'failed'
                    post.error_message = 'No board selected'
                    db.session.commit()
                    continue

                image_full_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'static', post.image_path)

                description = post.caption
                if post.hashtags:
                    description += '\n\n' + post.hashtags

                post.status = 'posting'
                db.session.commit()

                status_code, result = api.create_pin(
                    board_id=post.board_id,
                    title=post.title,
                    description=description,
                    link=post.pin_link,
                    image_path=image_full_path,
                )

                if status_code in (200, 201):
                    post.status = 'posted'
                    post.posted_at = datetime.now()
                    post.platform_post_id = result.get('id', '')
                    post.error_message = None
                    print(f"[AutoScheduler] Posted pin: {post.title[:30]}")
                else:
                    post.status = 'failed'
                    post.error_message = result.get('message', str(result))[:200]
                    print(f"[AutoScheduler] Pin failed: {post.error_message[:50]}")

                db.session.commit()

            except Exception as e:
                post.status = 'failed'
                post.error_message = str(e)[:200]
                db.session.commit()
                print(f"[AutoScheduler] Pin error: {str(e)[:50]}")
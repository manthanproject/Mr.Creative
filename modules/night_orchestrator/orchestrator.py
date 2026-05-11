"""
Night Orchestrator — Orchestrator (Brain)
Runs the full nightly cycle: TrendScout → CompetitorWatcher → PerformanceAnalyzer → ContentPlanner → ReportGenerator.
Scheduled via APScheduler to run at 11:00 PM IST daily.
Can also be triggered manually from the dashboard.
"""

import json
import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger('night_ops')

# ── Module-level state ──────────────────────────────────────────────
_cycle_lock = threading.Lock()
_current_cycle = {
    'running': False,
    'status': 'idle',           # idle, running, completed, failed
    'current_agent': None,
    'started_at': None,
    'progress': 0,              # 0-100
    'log': [],                  # [{time, agent, message}]
    'result': None,
}


def get_cycle_status() -> dict:
    """Return current cycle status (for dashboard polling)."""
    return dict(_current_cycle)


def is_running() -> bool:
    return _current_cycle['running']


def _log(agent: str, message: str):
    """Add an entry to the cycle log."""
    entry = {
        'time': datetime.now().strftime('%H:%M:%S'),
        'agent': agent,
        'message': message,
    }
    _current_cycle['log'].append(entry)
    logger.info(f"[{agent}] {message}")


# ═══════════════════════════════════════════════════════════════════
#  NIGHTLY CYCLE
# ═══════════════════════════════════════════════════════════════════

def run_nightly_cycle(app, manual: bool = False, niche: str = 'all'):
    """
    Full nightly cycle. Runs in a background thread.
    Call from APScheduler or manually from dashboard.
    """
    if not _cycle_lock.acquire(blocking=False):
        logger.warning("[Orchestrator] Cycle already running, skipping")
        return {'error': 'Cycle already running'}

    try:
        _current_cycle.update({
            'running': True,
            'status': 'running',
            'current_agent': 'Orchestrator',
            'started_at': datetime.now().isoformat(),
            'progress': 0,
            'log': [],
            'result': None,
        })

        start_time = time.time()
        trigger = 'manual' if manual else 'scheduled'
        _log('Orchestrator', f'Night cycle started ({trigger}, niche={niche})')

        errors = []
        trend_data = {}
        competitor_data = {}
        performance_data = {}
        content_plan = {}

        # ── Phase 1: TrendScout (0-25%) ──
        try:
            _current_cycle['current_agent'] = 'TrendScout'
            _current_cycle['progress'] = 5
            _log('TrendScout', 'Starting trend scan...')

            from modules.night_orchestrator.trend_scout import run_trend_scan
            trend_data = run_trend_scan(app, niche=niche)

            _current_cycle['progress'] = 25
            _log('TrendScout', f"Done — {trend_data.get('total_saved', 0)} trends saved")
        except Exception as e:
            _log('TrendScout', f'ERROR: {e}')
            errors.append({'agent': 'TrendScout', 'message': str(e)})

        # ── Phase 2: CompetitorWatcher (25-50%) ──
        try:
            _current_cycle['current_agent'] = 'CompetitorWatcher'
            _current_cycle['progress'] = 30
            _log('CompetitorWatcher', 'Starting competitor scan...')

            from modules.night_orchestrator.competitor_watcher import run_competitor_scan
            competitor_data = run_competitor_scan(app, niche=niche)

            _current_cycle['progress'] = 50
            _log('CompetitorWatcher', f"Done — {competitor_data.get('total_scanned', 0)} profiles scanned")
        except Exception as e:
            _log('CompetitorWatcher', f'ERROR: {e}')
            errors.append({'agent': 'CompetitorWatcher', 'message': str(e)})

        # ── Phase 3: PerformanceAnalyzer (50-65%) ──
        try:
            _current_cycle['current_agent'] = 'PerformanceAnalyzer'
            _current_cycle['progress'] = 55
            _log('PerformanceAnalyzer', 'Analyzing performance...')

            from modules.night_orchestrator.performance_analyzer import run_performance_analysis
            performance_data = run_performance_analysis(app)

            _current_cycle['progress'] = 65
            _log('PerformanceAnalyzer', 'Done — internal + external stats collected')
        except Exception as e:
            _log('PerformanceAnalyzer', f'ERROR: {e}')
            errors.append({'agent': 'PerformanceAnalyzer', 'message': str(e)})

        # ── Phase 4: ContentPlanner (65-85%) ──
        try:
            _current_cycle['current_agent'] = 'ContentPlanner'
            _current_cycle['progress'] = 70
            _log('ContentPlanner', 'Generating content plan via Groq...')

            from modules.night_orchestrator.content_planner import run_content_planning
            content_plan = run_content_planning(app, trend_data, competitor_data, performance_data)

            _current_cycle['progress'] = 85
            plan_count = content_plan.get('content_count', 0)
            if content_plan.get('error'):
                _log('ContentPlanner', f"Warning: {content_plan['error']}")
            else:
                _log('ContentPlanner', f'Done — {plan_count} content items planned')
        except Exception as e:
            _log('ContentPlanner', f'ERROR: {e}')
            errors.append({'agent': 'ContentPlanner', 'message': str(e)})

        # ── Phase 5: ReportGenerator (85-100%) ──
        try:
            _current_cycle['current_agent'] = 'ReportGenerator'
            _current_cycle['progress'] = 90
            _log('ReportGenerator', 'Compiling morning report...')

            elapsed = round((time.time() - start_time) / 60, 1)
            cycle_meta = {
                'duration_minutes': elapsed,
                'status': 'completed' if not errors else 'completed_with_errors',
                'trigger': trigger,
                'errors': errors,
            }

            from modules.night_orchestrator.report_generator import generate_morning_report
            report = generate_morning_report(
                app, trend_data, competitor_data, performance_data, content_plan, cycle_meta
            )

            _current_cycle['progress'] = 100
            _log('ReportGenerator', 'Morning report ready!')
        except Exception as e:
            _log('ReportGenerator', f'ERROR: {e}')
            errors.append({'agent': 'ReportGenerator', 'message': str(e)})
            report = None

        # ── Done ──
        elapsed = round((time.time() - start_time) / 60, 1)
        status = 'completed' if not errors else 'completed_with_errors'
        if len(errors) >= 4:
            status = 'failed'

        _current_cycle.update({
            'running': False,
            'status': status,
            'current_agent': None,
            'progress': 100,
            'result': {
                'duration_minutes': elapsed,
                'errors': errors,
                'report_summary': report.get('executive_summary', '') if report else 'Report generation failed',
            },
        })

        _log('Orchestrator', f'Night cycle {status} in {elapsed} minutes')
        return _current_cycle['result']

    except Exception as e:
        logger.error(f"[Orchestrator] Fatal error: {e}")
        _current_cycle.update({
            'running': False,
            'status': 'failed',
            'current_agent': None,
            'progress': 0,
        })
        _log('Orchestrator', f'FATAL: {e}')
        return {'error': str(e)}

    finally:
        _cycle_lock.release()


def run_nightly_cycle_async(app, manual: bool = False, niche: str = 'all'):
    """Run nightly cycle in a background thread."""
    thread = threading.Thread(
        target=run_nightly_cycle,
        args=(app,),
        kwargs={'manual': manual, 'niche': niche},
        daemon=True,
        name='night-orchestrator',
    )
    thread.start()
    return {'status': 'started', 'message': 'Night cycle started in background'}


# ═══════════════════════════════════════════════════════════════════
#  SCHEDULER INTEGRATION
# ═══════════════════════════════════════════════════════════════════

def init_night_scheduler(app):
    """
    Register the nightly cycle with APScheduler.
    Called from server.py during startup (local only, not Vercel).
    Runs at 23:00 IST daily.
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(
            func=run_nightly_cycle,
            trigger=CronTrigger(hour=23, minute=0),
            id='night_orchestrator',
            name='Night Orchestrator — Nightly Cycle',
            replace_existing=True,
            kwargs={'app': app, 'manual': False},
        )
        scheduler.start()
        logger.info("[Orchestrator] Scheduler registered — runs at 23:00 IST daily")

        import atexit
        atexit.register(lambda: scheduler.shutdown(wait=False))

    except Exception as e:
        logger.error(f"[Orchestrator] Scheduler init failed: {e}")

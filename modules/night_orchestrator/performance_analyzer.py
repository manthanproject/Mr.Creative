"""
Night Orchestrator — PerformanceAnalyzer
Analyzes own content performance:
  - Internal: generation stats, collection growth, prompt success rates
  - External: own Pinterest/IG post performance (via public scraping)
"""

import json
import logging
from datetime import datetime, timedelta
from collections import Counter

logger = logging.getLogger('night_ops')


def run_performance_analysis(app) -> dict:
    """
    Full performance analysis.
    Pulls internal stats from Mr.Creative DB + external social stats.
    Returns summary dict.
    """
    with app.app_context():
        internal = _analyze_internal_stats(app)
        external = _analyze_social_performance(app)

        return {
            'internal': internal,
            'external': external,
            'analysis_time': datetime.now().isoformat(),
        }


def _analyze_internal_stats(app) -> dict:
    """
    Analyze internal Mr.Creative stats:
    - Generations: total, success rate, by feature, recent trends
    - Prompts: most used types, approval rates
    - Collections: growth, popular ones
    - Queue: throughput, failure rates
    """
    from models import db, Generation, Prompt, Collection, SocialPost, JobQueue

    now = datetime.now()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)
    last_30d = now - timedelta(days=30)

    stats = {
        'period': 'last_30_days',
        'generations': {},
        'prompts': {},
        'collections': {},
        'social': {},
        'queue': {},
    }

    # ── Generation stats ──
    try:
        total_gens = Generation.query.count()
        recent_gens = Generation.query.filter(Generation.created_at >= last_7d).count()
        today_gens = Generation.query.filter(Generation.created_at >= last_24h).count()

        completed = Generation.query.filter_by(status='completed').count()
        failed = Generation.query.filter_by(status='failed').count()
        success_rate = round((completed / total_gens * 100), 1) if total_gens > 0 else 0

        # By feature breakdown
        feature_counts = {}
        for feat in ['campaign', 'photoshoot', 'animate']:
            feature_counts[feat] = Generation.query.filter_by(pomelli_feature=feat, status='completed').count()

        stats['generations'] = {
            'total': total_gens,
            'last_7d': recent_gens,
            'last_24h': today_gens,
            'completed': completed,
            'failed': failed,
            'success_rate': success_rate,
            'by_feature': feature_counts,
        }
    except Exception as e:
        logger.error(f"[PerfAnalyzer] Generation stats error: {e}")
        stats['generations'] = {'error': str(e)}

    # ── Prompt stats ──
    try:
        total_prompts = Prompt.query.count()
        approved = Prompt.query.filter_by(is_approved=True).count()
        favorited = Prompt.query.filter_by(is_favorite=True).count()

        # Type breakdown
        type_counts = {}
        for ptype in ['manual', 'generated', 'edited']:
            type_counts[ptype] = Prompt.query.filter_by(prompt_type=ptype).count()

        stats['prompts'] = {
            'total': total_prompts,
            'approved': approved,
            'favorited': favorited,
            'approval_rate': round((approved / total_prompts * 100), 1) if total_prompts > 0 else 0,
            'by_type': type_counts,
        }
    except Exception as e:
        logger.error(f"[PerfAnalyzer] Prompt stats error: {e}")
        stats['prompts'] = {'error': str(e)}

    # ── Collection stats ──
    try:
        total_collections = Collection.query.count()
        public_collections = Collection.query.filter_by(is_public=True).count()

        # Top collections by item count (manual count since it's a property)
        collections = Collection.query.all()
        top_collections = sorted(
            [{'name': c.name, 'items': c.item_count, 'id': c.id} for c in collections],
            key=lambda x: x['items'], reverse=True
        )[:5]

        stats['collections'] = {
            'total': total_collections,
            'public': public_collections,
            'top_collections': top_collections,
        }
    except Exception as e:
        logger.error(f"[PerfAnalyzer] Collection stats error: {e}")
        stats['collections'] = {'error': str(e)}

    # ── Social post stats ──
    try:
        total_posts = SocialPost.query.count()
        posted = SocialPost.query.filter_by(status='posted').count()
        failed_posts = SocialPost.query.filter_by(status='failed').count()
        scheduled = SocialPost.query.filter_by(status='scheduled').count()

        stats['social'] = {
            'total': total_posts,
            'posted': posted,
            'failed': failed_posts,
            'pending_scheduled': scheduled,
        }
    except Exception as e:
        logger.error(f"[PerfAnalyzer] Social stats error: {e}")
        stats['social'] = {'error': str(e)}

    # ── Queue throughput ──
    try:
        total_jobs = JobQueue.query.count()
        completed_jobs = JobQueue.query.filter_by(status='completed').count()
        failed_jobs = JobQueue.query.filter_by(status='failed').count()
        queued_jobs = JobQueue.query.filter_by(status='queued').count()

        stats['queue'] = {
            'total': total_jobs,
            'completed': completed_jobs,
            'failed': failed_jobs,
            'queued': queued_jobs,
            'throughput_rate': round((completed_jobs / total_jobs * 100), 1) if total_jobs > 0 else 0,
        }
    except Exception as e:
        logger.error(f"[PerfAnalyzer] Queue stats error: {e}")
        stats['queue'] = {'error': str(e)}

    return stats


def _analyze_social_performance(app) -> dict:
    """
    Analyze external social media performance.
    For now, uses competitor_watcher to scan own profiles.
    """
    from modules.night_orchestrator.competitor_watcher import scrape_instagram_profile, _get_session

    session = _get_session()
    own_profiles = {
        'instagram': {},
        'pinterest': {},
    }

    # Scan own Instagram
    try:
        ig_data = scrape_instagram_profile(session, 'dropy.in', 'https://www.instagram.com/dropy.in/')
        own_profiles['instagram'] = {
            'followers': ig_data.get('follower_count', 0),
            'posts': ig_data.get('post_count', 0),
            'avg_engagement': ig_data.get('avg_engagement', 0.0),
            'recent_posts': ig_data.get('recent_posts', [])[:3],
            'error': ig_data.get('error'),
        }
    except Exception as e:
        own_profiles['instagram'] = {'error': str(e)}

    return own_profiles

"""
Night Orchestrator — CompetitorWatcher
Monitors competitor Instagram and Pinterest pages using headless Chrome.
Tracks follower changes, recent posts, engagement rates.
"""

import json
import re
import time
import random
import logging
from datetime import datetime

logger = logging.getLogger('night_ops')

# ── Competitor list (configurable via dashboard later) ──────────────
# Format: (platform, handle, page_url)
DEFAULT_COMPETITORS = [
    # Pinterest — beauty/personal care niche
    ('pinterest', 'celobeauty', 'https://www.pinterest.com/celobeauty/'),
    ('pinterest', 'naborijanatl', 'https://www.pinterest.com/naborijanatl/'),
    # Instagram — beauty/skincare niche (public profiles)
    ('instagram', 'dropy.in', 'https://www.instagram.com/dropy.in/'),         # own page
    ('instagram', 'naborija_natural', 'https://www.instagram.com/naborija_natural/'),
]


def _polite_delay(min_s=2.0, max_s=5.0):
    time.sleep(random.uniform(min_s, max_s))


def _parse_count(text: str) -> int:
    """Parse follower/post counts like '1,234', '12.5K', '1.2M'."""
    text = text.strip().replace(',', '').replace(' ', '')
    multiplier = 1
    if text.upper().endswith('K'):
        multiplier = 1000
        text = text[:-1]
    elif text.upper().endswith('M'):
        multiplier = 1_000_000
        text = text[:-1]
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return 0


# ═══════════════════════════════════════════════════════════════════
#  PINTEREST PROFILE SCRAPER (Selenium)
# ═══════════════════════════════════════════════════════════════════

def scrape_pinterest_profile_selenium(driver, handle: str, page_url: str) -> dict:
    """Scrape a public Pinterest profile using Selenium."""
    result = {
        'platform': 'pinterest',
        'handle': handle,
        'page_url': page_url,
        'follower_count': 0,
        'following_count': 0,
        'pin_count': 0,
        'recent_pins': [],
        'avg_engagement': 0.0,
        'error': None,
    }

    try:
        driver.get(page_url)
        time.sleep(random.uniform(3, 5))

        page_text = driver.page_source

        # Strategy 1: Extract from meta description (Pinterest usually has this)
        meta_match = re.search(
            r'<meta\s+name="description"\s+content="([^"]*)"',
            page_text, re.IGNORECASE
        )
        if meta_match:
            desc = meta_match.group(1)
            follower_match = re.search(r'([\d,.]+[KkMm]?)\s*(?:followers?|Followers?)', desc)
            pin_match = re.search(r'([\d,.]+)\s*(?:pins?|Pins?)', desc)
            if follower_match:
                result['follower_count'] = _parse_count(follower_match.group(1))
            if pin_match:
                result['pin_count'] = _parse_count(pin_match.group(1))

        # Strategy 2: Extract from visible DOM text
        if result['follower_count'] == 0:
            try:
                body_text = driver.find_element('tag name', 'body').text
                follower_match = re.search(r'([\d,.]+[KkMm]?)\s*followers?', body_text, re.IGNORECASE)
                following_match = re.search(r'([\d,.]+[KkMm]?)\s*following', body_text, re.IGNORECASE)
                if follower_match:
                    result['follower_count'] = _parse_count(follower_match.group(1))
                if following_match:
                    result['following_count'] = _parse_count(following_match.group(1))
            except Exception:
                pass

        # Strategy 3: Extract from PWS_DATA JSON (if available in rendered source)
        if result['follower_count'] == 0:
            pws_match = re.search(r'"follower_count"\s*:\s*(\d+)', page_text)
            if pws_match:
                result['follower_count'] = int(pws_match.group(1))
            following_match = re.search(r'"following_count"\s*:\s*(\d+)', page_text)
            if following_match:
                result['following_count'] = int(following_match.group(1))
            pin_match = re.search(r'"pin_count"\s*:\s*(\d+)', page_text)
            if pin_match:
                result['pin_count'] = int(pin_match.group(1))

        logger.info(f"[CompetitorWatcher] Pinterest @{handle}: {result['follower_count']} followers")

        # ── Extract recent pins with engagement data ──
        try:
            # Scroll to load pins
            for _ in range(3):
                try:
                    driver.execute_script("window.scrollTo(0, document.body?.scrollHeight || 0)")
                except Exception:
                    pass
                time.sleep(1.5)

            # Extract pins from DOM
            pin_elements = driver.find_elements('css selector', 'div[data-test-id="pin"], div[role="listitem"]')
            if not pin_elements:
                pin_elements = driver.find_elements('css selector', 'a[href*="/pin/"]')

            for pin_el in pin_elements[:12]:
                try:
                    pin_data = {}

                    # Get pin link
                    try:
                        link_el = pin_el if pin_el.tag_name == 'a' else pin_el.find_element('css selector', 'a[href*="/pin/"]')
                        pin_data['url'] = link_el.get_attribute('href') or ''
                    except Exception:
                        pin_data['url'] = ''

                    # Get image
                    try:
                        img_el = pin_el.find_element('css selector', 'img[src*="pinimg.com"]')
                        pin_data['image'] = img_el.get_attribute('src') or ''
                        pin_data['title'] = (img_el.get_attribute('alt') or '').strip()[:150]
                    except Exception:
                        pin_data['image'] = ''
                        pin_data['title'] = ''

                    # Get save/repin count if visible
                    try:
                        pin_text = pin_el.text
                        save_match = re.search(r'([\d,.]+[KkMm]?)\s*(?:saves?|repins?)', pin_text, re.IGNORECASE)
                        if save_match:
                            pin_data['saves'] = _parse_count(save_match.group(1))
                        else:
                            pin_data['saves'] = 0
                    except Exception:
                        pin_data['saves'] = 0

                    if pin_data.get('title') or pin_data.get('image'):
                        result['recent_pins'].append(pin_data)

                except Exception:
                    continue

            # Calculate avg engagement from saves
            if result['recent_pins'] and result['follower_count'] > 0:
                total_saves = sum(p.get('saves', 0) for p in result['recent_pins'])
                result['avg_engagement'] = round(
                    (total_saves / len(result['recent_pins'])) / max(result['follower_count'], 1) * 100, 2
                )

            logger.info(f"[CompetitorWatcher] Pinterest @{handle}: {len(result['recent_pins'])} pins extracted")
        except Exception as e:
            logger.warning(f"[CompetitorWatcher] Pinterest pin extraction error for {handle}: {e}")

    except Exception as e:
        result['error'] = str(e)
        logger.error(f"[CompetitorWatcher] Pinterest error for {handle}: {e}")

    return result


# ═══════════════════════════════════════════════════════════════════
#  INSTAGRAM PROFILE SCRAPER (Selenium)
# ═══════════════════════════════════════════════════════════════════

def scrape_instagram_profile_selenium(driver, handle: str, page_url: str) -> dict:
    """Scrape a public Instagram profile using Selenium."""
    result = {
        'platform': 'instagram',
        'handle': handle,
        'page_url': page_url,
        'follower_count': 0,
        'following_count': 0,
        'post_count': 0,
        'recent_posts': [],
        'avg_engagement': 0.0,
        'bio': '',
        'error': None,
    }

    try:
        driver.get(page_url)
        time.sleep(random.uniform(4, 6))

        page_text = driver.page_source

        # Strategy 1: og:description meta tag (most reliable)
        # Format: "1,234 Followers, 567 Following, 89 Posts - ..."
        og_match = re.search(
            r'<meta\s+(?:property|name)="og:description"\s+content="([^"]*)"',
            page_text, re.IGNORECASE
        )
        if og_match:
            content = og_match.group(1)
            follower_match = re.search(r'([\d,.]+[KkMm]?)\s*Followers', content)
            following_match = re.search(r'([\d,.]+[KkMm]?)\s*Following', content)
            post_match = re.search(r'([\d,.]+)\s*Posts', content)

            if follower_match:
                result['follower_count'] = _parse_count(follower_match.group(1))
            if following_match:
                result['following_count'] = _parse_count(following_match.group(1))
            if post_match:
                result['post_count'] = _parse_count(post_match.group(1))

        # Strategy 2: Visible profile header stats
        if result['follower_count'] == 0:
            try:
                header = driver.find_element('tag name', 'header')
                header_text = header.text
                follower_match = re.search(r'([\d,.]+[KkMm]?)\s*followers?', header_text, re.IGNORECASE)
                following_match = re.search(r'([\d,.]+[KkMm]?)\s*following', header_text, re.IGNORECASE)
                post_match = re.search(r'([\d,.]+)\s*posts?', header_text, re.IGNORECASE)

                if follower_match:
                    result['follower_count'] = _parse_count(follower_match.group(1))
                if following_match:
                    result['following_count'] = _parse_count(following_match.group(1))
                if post_match:
                    result['post_count'] = _parse_count(post_match.group(1))
            except Exception:
                pass

        # Strategy 3: JSON in page source
        if result['follower_count'] == 0:
            fc_match = re.search(r'"edge_followed_by"\s*:\s*\{\s*"count"\s*:\s*(\d+)', page_text)
            if fc_match:
                result['follower_count'] = int(fc_match.group(1))
            fg_match = re.search(r'"edge_follow"\s*:\s*\{\s*"count"\s*:\s*(\d+)', page_text)
            if fg_match:
                result['following_count'] = int(fg_match.group(1))

        # Bio from og:title
        title_match = re.search(
            r'<meta\s+(?:property|name)="og:title"\s+content="([^"]*)"',
            page_text, re.IGNORECASE
        )
        if title_match:
            parts = title_match.group(1).split(' • ')
            result['bio'] = parts[-1] if len(parts) > 1 else ''

        logger.info(f"[CompetitorWatcher] IG @{handle}: {result['follower_count']} followers")

    except Exception as e:
        result['error'] = str(e)
        logger.error(f"[CompetitorWatcher] Instagram error for {handle}: {e}")

    return result


# ═══════════════════════════════════════════════════════════════════
#  STANDALONE FUNCTION (used by performance_analyzer.py)
# ═══════════════════════════════════════════════════════════════════

def scrape_instagram_profile(session, handle: str, page_url: str) -> dict:
    """
    Standalone IG scraper — creates its own driver, scrapes, quits.
    Kept for backward compatibility with performance_analyzer.py.
    The 'session' param is ignored (Selenium doesn't need it).
    """
    driver = None
    try:
        from modules.night_orchestrator.browser import create_headless_driver
        driver = create_headless_driver()
        return scrape_instagram_profile_selenium(driver, handle, page_url)
    except Exception as e:
        logger.error(f"[CompetitorWatcher] Standalone IG scrape error: {e}")
        return {
            'platform': 'instagram', 'handle': handle, 'page_url': page_url,
            'follower_count': 0, 'following_count': 0, 'post_count': 0,
            'recent_posts': [], 'avg_engagement': 0.0, 'bio': '', 'error': str(e),
        }
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def _get_session():
    """Kept for backward compat — not used by Selenium scrapers."""
    import requests as req
    return req.Session()


# ═══════════════════════════════════════════════════════════════════
#  MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════

def run_competitor_scan(app, competitors: list[tuple] | None = None) -> dict:
    """
    Full competitor scan using a single shared headless Chrome.
    Saves results to night_competitors table.
    """
    with app.app_context():
        from models import db, NightCompetitor

        # Read from DB (WatchedCompetitor), fallback to DEFAULT_COMPETITORS
        if competitors is None:
            try:
                from models import WatchedCompetitor
                watched = WatchedCompetitor.query.all()
                if watched:
                    competitors = [(w.platform, w.handle, w.page_url) for w in watched]
                else:
                    competitors = DEFAULT_COMPETITORS
            except Exception:
                competitors = DEFAULT_COMPETITORS
        scan_time = datetime.now()
        results = []
        driver = None

        try:
            from modules.night_orchestrator.browser import create_headless_driver
            driver = create_headless_driver()
            logger.info("[CompetitorWatcher] Headless Chrome started")

            for platform, handle, page_url in competitors:
                logger.info(f"[CompetitorWatcher] Scanning {platform}/{handle}")

                if platform == 'pinterest':
                    data = scrape_pinterest_profile_selenium(driver, handle, page_url)
                elif platform == 'instagram':
                    data = scrape_instagram_profile_selenium(driver, handle, page_url)
                else:
                    logger.warning(f"[CompetitorWatcher] Unknown platform: {platform}")
                    continue

                results.append(data)

                # Save to DB
                try:
                    comp = NightCompetitor(
                        platform=platform,
                        handle=handle,
                        page_url=page_url,
                        last_post_data=json.dumps(data, ensure_ascii=False),
                        follower_count=data.get('follower_count', 0),
                        avg_engagement=data.get('avg_engagement', 0.0),
                        scanned_at=scan_time,
                    )
                    db.session.add(comp)
                except Exception as e:
                    logger.error(f"[CompetitorWatcher] DB save error for {handle}: {e}")

                _polite_delay()

        except Exception as e:
            logger.error(f"[CompetitorWatcher] Selenium init error: {e}")
        finally:
            if driver:
                try:
                    driver.quit()
                    logger.info("[CompetitorWatcher] Headless Chrome closed")
                except Exception:
                    pass

        db.session.commit()
        logger.info(f"[CompetitorWatcher] Scanned {len(results)} competitors")

        return {
            'total_scanned': len(results),
            'scan_time': scan_time.isoformat(),
            'results': results,
            'errors': [r for r in results if r.get('error')],
        }

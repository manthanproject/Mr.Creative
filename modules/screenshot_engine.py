"""
Mr.Creative Screenshot Engine
Renders HTML strings to PNG using Playwright (Chromium).

Usage:
    from modules.screenshot_engine import render_html_to_png

    path = render_html_to_png(
        html_string='<html>...</html>',
        output_path='output.png',
        width=1200,
        height=628,
    )

Setup (one-time):
    pip install playwright
    playwright install chromium
"""

import os
import tempfile


def render_html_to_png(html_string, output_path, width=1200, height=800,
                        device_scale=2, wait_ms=500):
    """Render HTML string to PNG using Playwright.

    Args:
        html_string: Full HTML document string
        output_path: Where to save the PNG
        width: Viewport width in pixels
        height: Viewport height (use 0 for auto-height based on content)
        device_scale: Pixel density (2 = retina quality)
        wait_ms: Wait time after load for fonts/CSS to settle

    Returns:
        output_path on success, None on failure
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[Screenshot] playwright not installed — pip install playwright && playwright install chromium")
        return None

    # Write HTML to temp file (Playwright needs a file:// URL for local HTML)
    tmp_html = None
    try:
        tmp_html = tempfile.NamedTemporaryFile(
            mode='w', suffix='.html', delete=False, encoding='utf-8'
        )
        tmp_html.write(html_string)
        tmp_html.close()

        file_url = f'file:///{tmp_html.name.replace(os.sep, "/")}'

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                viewport={'width': width, 'height': height or 800},
                device_scale_factor=device_scale,
            )

            page.goto(file_url, wait_until='networkidle')

            # Wait for fonts to load
            if wait_ms > 0:
                page.wait_for_timeout(wait_ms)

            # Screenshot options
            if height == 0:
                # Auto-height: screenshot full page
                page.screenshot(path=output_path, full_page=True)
            else:
                # Fixed height: clip to viewport
                page.screenshot(
                    path=output_path,
                    clip={'x': 0, 'y': 0, 'width': width, 'height': height},
                )

            browser.close()

        print(f"[Screenshot] Rendered: {os.path.basename(output_path)} ({width}x{height})")
        return output_path

    except Exception as e:
        print(f"[Screenshot] Error: {e}")
        import traceback
        traceback.print_exc()
        return None

    finally:
        if tmp_html and os.path.exists(tmp_html.name):
            try:
                os.unlink(tmp_html.name)
            except Exception:
                pass


def render_template_to_png(template_func, output_path, template_kwargs=None,
                            device_scale=2, wait_ms=500):
    """Convenience wrapper: calls a template function → renders to PNG.

    Args:
        template_func: Function from html_templates.py (e.g. aplus_template)
        output_path: Where to save the PNG
        template_kwargs: Dict of template arguments
        device_scale: Pixel density
        wait_ms: Wait time

    Returns:
        output_path on success, None on failure
    """
    kwargs = template_kwargs or {}
    html = template_func(**kwargs)

    # Extract width/height from kwargs (templates define their own defaults)
    width = kwargs.get('width', 1200)
    height = kwargs.get('height', 800)

    return render_html_to_png(
        html_string=html,
        output_path=output_path,
        width=width,
        height=height,
        device_scale=device_scale,
        wait_ms=wait_ms,
    )

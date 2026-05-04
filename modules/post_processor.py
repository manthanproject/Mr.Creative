"""
Mr.Creative Post-Processor (Agent 5)
Applies brand elements to generated images:
1. rembg background removal (optional)
2. Logo placement from BrandKit
3. Text overlays (headline, subheadline, CTA)
4. Color border/frame using brand colors

Learnings applied from:
- danielgatis/rembg: remove() API, post_process_mask for clean edges
- Orangeliquid/Watermark-Application: RGBA overlay + alpha_composite pattern
- tbobm/watermarking: paste(overlay, pos, overlay) for logo alpha
"""

import os
import io
import json
import hashlib
import urllib.request
from typing import Any
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

# ═══════════════════════════════════════════
# Font Management — Google Fonts TTF download
# ═══════════════════════════════════════════

FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'fonts')

# Map of common Google Font names → direct TTF download URLs
# Using fonts.google.com CDN — these are the Regular (400) weight files
GOOGLE_FONT_URLS = {
    'Poppins': 'https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Regular.ttf',
    'Poppins-Bold': 'https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf',
    'Poppins-SemiBold': 'https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-SemiBold.ttf',
    'Inter': 'https://github.com/google/fonts/raw/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf',
    'Roboto': 'https://github.com/google/fonts/raw/main/ofl/roboto/Roboto%5Bwdth%2Cwght%5D.ttf',
    'Montserrat': 'https://github.com/google/fonts/raw/main/ofl/montserrat/Montserrat%5Bwght%5D.ttf',
    'Lato': 'https://github.com/google/fonts/raw/main/ofl/lato/Lato-Regular.ttf',
    'Lato-Bold': 'https://github.com/google/fonts/raw/main/ofl/lato/Lato-Bold.ttf',
    'Playfair Display': 'https://github.com/google/fonts/raw/main/ofl/playfairdisplay/PlayfairDisplay%5Bwght%5D.ttf',
    'Raleway': 'https://github.com/google/fonts/raw/main/ofl/raleway/Raleway%5Bwght%5D.ttf',
    'Open Sans': 'https://github.com/google/fonts/raw/main/ofl/opensans/OpenSans%5Bwdth%2Cwght%5D.ttf',
    'Nunito': 'https://github.com/google/fonts/raw/main/ofl/nunito/Nunito%5Bwght%5D.ttf',
}


def _ensure_fonts_dir():
    """Create fonts directory if it doesn't exist."""
    os.makedirs(FONTS_DIR, exist_ok=True)


def _get_font_path(font_name, bold=False):
    """Get local TTF path for a Google Font, downloading if needed.
    Falls back to system Arial/DejaVu if download fails."""
    _ensure_fonts_dir()

    # Check bold variant
    lookup_key = f'{font_name}-Bold' if bold else font_name
    if lookup_key not in GOOGLE_FONT_URLS and font_name not in GOOGLE_FONT_URLS:
        # Try SemiBold for heading
        if bold:
            lookup_key = f'{font_name}-SemiBold'
        if lookup_key not in GOOGLE_FONT_URLS:
            lookup_key = font_name

    safe_name = lookup_key.replace(' ', '_')
    local_path = os.path.join(FONTS_DIR, f'{safe_name}.ttf')

    if os.path.exists(local_path):
        return local_path

    url = GOOGLE_FONT_URLS.get(lookup_key)
    if url:
        try:
            print(f"[PostProcessor] Downloading font: {lookup_key}")
            urllib.request.urlretrieve(url, local_path)
            return local_path
        except Exception as e:
            print(f"[PostProcessor] Font download failed for {lookup_key}: {e}")

    # Fallback to system fonts
    for fallback in [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        'C:/Windows/Fonts/arial.ttf',
        'C:/Windows/Fonts/arialbd.ttf',
    ]:
        if os.path.exists(fallback):
            return fallback

    return None  # PIL will use default bitmap font


def _load_font(font_name, size, bold=False):
    """Load a font at given size. Returns ImageFont."""
    path = _get_font_path(font_name, bold=bold)
    try:
        if path:
            return ImageFont.truetype(path, size)
    except Exception as e:
        print(f"[PostProcessor] Font load error: {e}")
    return ImageFont.load_default()


# ═══════════════════════════════════════════
# Color Utilities
# ═══════════════════════════════════════════

def _hex_to_rgba(hex_color, alpha=255):
    """Convert hex color (#RRGGBB) to RGBA tuple."""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 6:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return (r, g, b, alpha)
    return (0, 0, 0, alpha)


def _contrast_color(hex_color):
    """Return black or white depending on which has better contrast."""
    r, g, b, _ = _hex_to_rgba(hex_color)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return '#FFFFFF' if luminance < 0.5 else '#000000'


def _darken(hex_color, factor=0.3):
    """Darken a hex color by factor (0-1)."""
    r, g, b, _ = _hex_to_rgba(hex_color)
    return (int(r * (1 - factor)), int(g * (1 - factor)), int(b * (1 - factor)), 255)


# ═══════════════════════════════════════════
# PostProcessor Class
# ═══════════════════════════════════════════

class PostProcessor:
    """Applies brand elements to generated images."""

    def __init__(self, brand_kit):
        """
        Args:
            brand_kit: BrandKit model instance with colors, fonts, logo_path
        """
        self.brand = brand_kit
        self.primary = brand_kit.primary_color or '#000000'
        self.secondary = brand_kit.secondary_color or '#FFFFFF'
        self.accent = brand_kit.accent_color or '#C1CD7D'
        self.heading_font = brand_kit.heading_font or 'Poppins'
        self.body_font = brand_kit.body_font or 'Inter'
        self._rembg_session: Any = None

    # ═══════════════════════════════════════
    # Step 0: rembg Background Removal
    # ═══════════════════════════════════════

    def _get_rembg_session(self):
        """Lazy-load rembg session (downloads ~170MB model on first use)."""
        if self._rembg_session is None:
            try:
                from rembg import new_session
                self._rembg_session = new_session('u2net')
                print("[PostProcessor] rembg session loaded (u2net)")
            except ImportError:
                print("[PostProcessor] rembg not installed — pip install rembg[cpu]")
                return None
            except Exception as e:
                print(f"[PostProcessor] rembg init error: {e}")
                return None
        return self._rembg_session

    def remove_background(self, image_path, output_path=None):
        """Remove background from image using rembg.

        Args:
            image_path: Path to input image
            output_path: Path to save result (default: same path with _nobg suffix)

        Returns:
            Path to output image, or None on failure
        """
        session = self._get_rembg_session()
        if not session:
            return None

        try:
            from rembg import remove

            img = Image.open(image_path)
            result = remove(
                img,
                session=session,
                post_process_mask=True,  # Smoother edges
            )

            if output_path is None:
                base, ext = os.path.splitext(image_path)
                output_path = f'{base}_nobg.png'

            if not hasattr(result, 'save'):
                result = Image.fromarray(result)  # pyrefly: ignore
            result.save(output_path, 'PNG')  # pyrefly: ignore
            print(f"[PostProcessor] Background removed: {os.path.basename(output_path)}")
            return output_path

        except Exception as e:
            print(f"[PostProcessor] rembg error: {e}")
            return None

    def clean_reference_image(self, ref_image_path):
        """Clean reference image before sending to Flow bot.
        Removes background → saves as _clean.png next to original.

        Args:
            ref_image_path: Path to reference product photo

        Returns:
            Path to cleaned image, or original path on failure
        """
        if not ref_image_path or not os.path.exists(ref_image_path):
            return ref_image_path

        base, ext = os.path.splitext(ref_image_path)
        clean_path = f'{base}_clean.png'

        # Skip if already cleaned
        if os.path.exists(clean_path):
            print(f"[PostProcessor] Using cached clean reference: {os.path.basename(clean_path)}")
            return clean_path

        result = self.remove_background(ref_image_path, clean_path)
        return result or ref_image_path

    # ═══════════════════════════════════════
    # Step 1: Logo Placement
    # ═══════════════════════════════════════

    def _get_logo(self):
        """Load brand logo as RGBA PIL Image."""
        if not self.brand.logo_path:
            return None

        logo_abs = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'static', self.brand.logo_path
        )
        if not os.path.exists(logo_abs):
            print(f"[PostProcessor] Logo not found: {logo_abs}")
            return None

        try:
            logo = Image.open(logo_abs).convert('RGBA')
            return logo
        except Exception as e:
            print(f"[PostProcessor] Logo load error: {e}")
            return None

    def add_logo(self, img, position='bottom-right', max_width_pct=0.15, opacity=230):
        """Place brand logo on image.

        Args:
            img: PIL Image (RGBA)
            position: top-left, top-right, bottom-left, bottom-right, center
            max_width_pct: Max logo width as % of image width (default 15%)
            opacity: Logo opacity 0-255

        Returns:
            PIL Image with logo
        """
        logo = self._get_logo()
        if logo is None:
            return img

        img = img.convert('RGBA')

        # Scale logo to max_width_pct of image width, maintain aspect ratio
        max_w = int(img.width * max_width_pct)
        if logo.width > max_w:
            ratio = max_w / logo.width
            new_h = int(logo.height * ratio)
            logo = logo.resize((max_w, new_h), Image.LANCZOS)  # pyrefly: ignore

        # Apply opacity to logo
        if opacity < 255:
            alpha = logo.split()[3]
            alpha = alpha.point(lambda p: int(p * opacity / 255))
            logo.putalpha(alpha)

        # Calculate position
        margin = int(img.width * 0.03)  # 3% margin
        positions = {
            'top-left': (margin, margin),
            'top-right': (img.width - logo.width - margin, margin),
            'bottom-left': (margin, img.height - logo.height - margin),
            'bottom-right': (img.width - logo.width - margin, img.height - logo.height - margin),
            'center': ((img.width - logo.width) // 2, (img.height - logo.height) // 2),
        }
        x, y = positions.get(position, positions['bottom-right'])

        # Paste with alpha mask (from tbobm/watermarking pattern)
        img.paste(logo, (x, y), logo)
        return img

    # ═══════════════════════════════════════
    # Step 2: Text Overlays
    # ═══════════════════════════════════════

    def _draw_text_with_shadow(self, draw, pos, text, font, fill, shadow_color=None, shadow_offset=2):
        """Draw text with drop shadow for readability."""
        x, y = pos
        if shadow_color:
            draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=shadow_color)
        draw.text((x, y), text, font=font, fill=fill)

    def _wrap_text(self, text, font, max_width, draw):
        """Word-wrap text to fit within max_width."""
        words = text.split()
        lines = []
        current_line = ''

        for word in words:
            test_line = f'{current_line} {word}'.strip()
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)
        return lines

    def add_text_overlay(self, img, headline='', subheadline='', cta='',
                         text_zone='bottom', text_color=None):
        """Add text overlays (headline, subheadline, CTA) on image.

        Uses RGBA overlay layer + alpha_composite (from Watermark-Application pattern).

        Args:
            img: PIL Image
            headline: Main headline text
            subheadline: Secondary text
            cta: Call-to-action text
            text_zone: Where to place text — bottom, top, center
            text_color: Override text color (hex), auto-picks contrast if None

        Returns:
            PIL Image with text
        """
        if not headline and not subheadline and not cta:
            return img

        img = img.convert('RGBA')
        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Text sizing relative to image
        w, h = img.size
        margin_x = int(w * 0.06)
        max_text_w = w - (margin_x * 2)

        headline_size = max(24, int(h * 0.06))
        sub_size = max(16, int(h * 0.035))
        cta_size = max(18, int(h * 0.04))

        # Load fonts
        h_font = _load_font(self.heading_font, headline_size, bold=True)
        s_font = _load_font(self.body_font, sub_size)
        c_font = _load_font(self.heading_font, cta_size, bold=True)

        # Calculate total text block height
        line_gap = int(headline_size * 0.4)
        text_blocks = []

        if headline:
            lines = self._wrap_text(headline, h_font, max_text_w, draw)
            block_h = sum(draw.textbbox((0, 0), l, font=h_font)[3] for l in lines) + line_gap * (len(lines) - 1)
            text_blocks.append(('headline', lines, h_font, block_h))

        if subheadline:
            lines = self._wrap_text(subheadline, s_font, max_text_w, draw)
            block_h = sum(draw.textbbox((0, 0), l, font=s_font)[3] for l in lines) + (line_gap // 2) * (len(lines) - 1)
            text_blocks.append(('sub', lines, s_font, block_h))

        if cta:
            text_blocks.append(('cta', [cta], c_font, draw.textbbox((0, 0), cta, font=c_font)[3]))

        total_h = sum(b[3] for b in text_blocks) + line_gap * len(text_blocks)

        # Position based on text_zone
        if text_zone == 'top':
            start_y = int(h * 0.08)
        elif text_zone == 'center':
            start_y = (h - total_h) // 2
        else:  # bottom
            start_y = h - total_h - int(h * 0.08)

        # Semi-transparent backdrop behind text
        pad = int(h * 0.02)
        backdrop_y1 = max(0, start_y - pad)
        backdrop_y2 = min(h, start_y + total_h + pad)
        draw.rectangle(
            [(0, backdrop_y1), (w, backdrop_y2)],
            fill=(0, 0, 0, 120)
        )

        # Determine text color
        if text_color:
            fill = _hex_to_rgba(text_color)
        else:
            fill = (255, 255, 255, 255)  # White on dark backdrop

        shadow = (0, 0, 0, 180)
        accent_fill = _hex_to_rgba(self.accent)

        # Draw text blocks
        y = start_y
        for block_type, lines, font, block_h in text_blocks:
            for line in lines:
                if block_type == 'cta':
                    # CTA gets accent color + pill background
                    bbox = draw.textbbox((0, 0), line, font=font)
                    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                    pill_x = (w - tw) // 2 - int(tw * 0.2)
                    pill_w = tw + int(tw * 0.4)
                    pill_h = th + int(th * 0.6)
                    pill_y = y - int(th * 0.3)
                    draw.rounded_rectangle(
                        [(pill_x, pill_y), (pill_x + pill_w, pill_y + pill_h)],
                        radius=int(pill_h * 0.4),
                        fill=_hex_to_rgba(self.accent, 220)
                    )
                    cta_color = _hex_to_rgba(_contrast_color(self.accent))
                    draw.text(((w - tw) // 2, y), line, font=font, fill=cta_color)
                else:
                    bbox = draw.textbbox((0, 0), line, font=font)
                    tw = bbox[2] - bbox[0]
                    x = (w - tw) // 2  # Center text
                    self._draw_text_with_shadow(draw, (x, y), line, font, fill, shadow)

                line_h = draw.textbbox((0, 0), line, font=font)[3]
                y += line_h + (line_gap if block_type == 'headline' else line_gap // 2)

            y += line_gap

        # Composite overlay onto image
        result = Image.alpha_composite(img, overlay)
        return result

    # ═══════════════════════════════════════
    # Step 3: Color Border
    # ═══════════════════════════════════════

    def add_border(self, img, border_style='solid', border_color=None, width_pct=0.03):
        """Add colored border/frame around image.

        Args:
            img: PIL Image
            border_style: 'solid', 'gradient', or 'none'
            border_color: Hex color (default: brand primary)
            width_pct: Border width as % of image width (default 3%)

        Returns:
            PIL Image with border
        """
        if border_style == 'none':
            return img

        img = img.convert('RGBA')
        w, h = img.size
        border_w = max(4, int(w * width_pct))

        color = border_color or self.primary
        rgba = _hex_to_rgba(color)

        if border_style == 'gradient':
            # Gradient border: primary → secondary
            new_w = w + border_w * 2
            new_h = h + border_w * 2
            bordered = Image.new('RGBA', (new_w, new_h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(bordered)

            primary_rgba = _hex_to_rgba(self.primary)
            secondary_rgba = _hex_to_rgba(self.secondary)

            # Draw gradient as horizontal bands
            for i in range(new_h):
                ratio = i / new_h
                r = int(primary_rgba[0] + (secondary_rgba[0] - primary_rgba[0]) * ratio)
                g = int(primary_rgba[1] + (secondary_rgba[1] - primary_rgba[1]) * ratio)
                b = int(primary_rgba[2] + (secondary_rgba[2] - primary_rgba[2]) * ratio)
                draw.line([(0, i), (new_w, i)], fill=(r, g, b, 255))

            bordered.paste(img, (border_w, border_w))
            return bordered

        else:
            # Solid border using ImageOps.expand
            rgb_img = img.convert('RGB')
            bordered = ImageOps.expand(rgb_img, border=border_w, fill=rgba[:3])
            return bordered.convert('RGBA')

    # ═══════════════════════════════════════
    # Full Pipeline — process_image()
    # ═══════════════════════════════════════

    def process_image(self, image_path, plan_item, output_path=None):
        """Run full post-processing pipeline on a single image.

        Args:
            image_path: Path to generated image
            plan_item: Dict from content plan with keys:
                - remove_background (bool)
                - needs_logo (bool)
                - logo_position (str)
                - text_overlay (bool)
                - headline, subheadline, cta (str)
                - text_safe_zone (str): bottom/top/center
                - border_style (str): none/solid/gradient
            output_path: Where to save (default: overwrites original)

        Returns:
            Path to processed image, or original on failure
        """
        if not os.path.exists(image_path):
            print(f"[PostProcessor] Image not found: {image_path}")
            return image_path

        try:
            img = Image.open(image_path).convert('RGBA')
            changed = False

            # Step 0: Background removal
            if plan_item.get('remove_background', False):
                result_path = self.remove_background(image_path)
                if result_path:
                    img = Image.open(result_path).convert('RGBA')
                    changed = True

            # Step 1: Logo placement
            if plan_item.get('needs_logo', False) and self.brand.logo_path:
                position = plan_item.get('logo_position', 'bottom-right')
                img = self.add_logo(img, position=position)
                changed = True

            # Step 2: Text overlays
            if plan_item.get('text_overlay', False):
                headline = plan_item.get('headline', '')
                subheadline = plan_item.get('subheadline', '')
                cta = plan_item.get('cta', '')
                zone = plan_item.get('text_safe_zone', 'bottom')

                if headline or subheadline or cta:
                    img = self.add_text_overlay(
                        img,
                        headline=headline,
                        subheadline=subheadline,
                        cta=cta,
                        text_zone=zone,
                    )
                    changed = True

            # Step 3: Border
            border_style = plan_item.get('border_style', 'none')
            if border_style and border_style != 'none':
                img = self.add_border(img, border_style=border_style)
                changed = True

            # Save
            if changed:
                save_path = output_path or image_path
                # Save as PNG to preserve alpha, or JPEG if original was JPEG
                if save_path.lower().endswith(('.jpg', '.jpeg')):
                    img = img.convert('RGB')
                    img.save(save_path, 'JPEG', quality=95)
                else:
                    img.save(save_path, 'PNG')
                print(f"[PostProcessor] Processed: {os.path.basename(save_path)}")
                return save_path

            return image_path

        except Exception as e:
            print(f"[PostProcessor] Error processing {os.path.basename(image_path)}: {e}")
            import traceback
            traceback.print_exc()
            return image_path

    def process_batch(self, results, content_plan, output_dir):
        """Process all generated images in a batch.

        Args:
            results: List of result dicts with 'path' and 'filename'
            content_plan: List of plan dicts from Agent 2
            output_dir: Directory containing the images

        Returns:
            Updated results list with processed paths
        """
        processed = []
        for i, result in enumerate(results):
            if 'error' in result:
                processed.append(result)
                continue

            filename = result.get('filename', '')
            image_path = os.path.join(output_dir, filename) if filename else None

            if not image_path or not os.path.exists(image_path):
                processed.append(result)
                continue

            # Get corresponding plan item
            plan_idx = result.get('id', i + 1) - 1
            plan_item = content_plan[plan_idx] if plan_idx < len(content_plan) else {}

            # Process image
            out_path = self.process_image(image_path, plan_item)

            # Update result if path changed (e.g., extension changed to .png)
            if out_path != image_path:
                new_filename = os.path.basename(out_path)
                rel_path = result.get('path', '').rsplit('/', 1)[0] + '/' + new_filename
                result['filename'] = new_filename
                result['path'] = rel_path
                result['post_processed'] = True

            processed.append(result)

        print(f"[PostProcessor] Batch done: {len([r for r in processed if r.get('post_processed')])} images processed")
        return processed

"""
Mr.Creative Color Correction
Auto brightness/contrast, white balance, and brand color tinting.
Pure Pillow — no OpenCV dependency needed.
"""

import os
from PIL import Image, ImageEnhance, ImageFilter, ImageStat, ImageDraw


def auto_enhance(img, brightness=None, contrast=None, saturation=None, sharpness=None):
    """Auto-enhance image with optional manual overrides.

    Args:
        img: PIL Image
        brightness: 0.0-2.0 (1.0 = unchanged, None = auto)
        contrast: 0.0-2.0 (1.0 = unchanged, None = auto)
        saturation: 0.0-2.0 (1.0 = unchanged, None = auto)
        sharpness: 0.0-2.0 (1.0 = unchanged, None = auto)

    Returns:
        Enhanced PIL Image
    """
    img = img.convert('RGB')

    # Auto-detect values if not provided
    if brightness is None:
        brightness = _auto_brightness(img)
    if contrast is None:
        contrast = _auto_contrast(img)
    if saturation is None:
        saturation = 1.1  # Slight boost default
    if sharpness is None:
        sharpness = 1.15  # Slight sharpen default

    img = ImageEnhance.Brightness(img).enhance(brightness)
    img = ImageEnhance.Contrast(img).enhance(contrast)
    img = ImageEnhance.Color(img).enhance(saturation)
    img = ImageEnhance.Sharpness(img).enhance(sharpness)

    return img


def _auto_brightness(img):
    """Calculate brightness correction factor.
    Target mean brightness ~128 (mid-gray)."""
    stat = ImageStat.Stat(img)
    mean_brightness = sum(stat.mean[:3]) / 3
    if mean_brightness < 80:
        return min(1.4, 128 / max(mean_brightness, 1))
    elif mean_brightness > 180:
        return max(0.7, 128 / mean_brightness)
    return 1.0


def _auto_contrast(img):
    """Calculate contrast correction based on standard deviation.
    Low stddev = flat/washed → boost contrast."""
    stat = ImageStat.Stat(img)
    mean_stddev = sum(stat.stddev[:3]) / 3
    if mean_stddev < 40:
        return 1.3  # Flat image, boost
    elif mean_stddev < 55:
        return 1.15  # Slightly flat
    elif mean_stddev > 80:
        return 0.9  # Too contrasty, reduce
    return 1.0


def auto_white_balance(img):
    """Simple gray-world white balance.
    Scales each channel so the average is gray (128)."""
    img = img.convert('RGB')
    stat = ImageStat.Stat(img)
    avg_r, avg_g, avg_b = stat.mean[:3]
    avg_all = (avg_r + avg_g + avg_b) / 3

    # Scale factors
    scale_r = avg_all / max(avg_r, 1)
    scale_g = avg_all / max(avg_g, 1)
    scale_b = avg_all / max(avg_b, 1)

    # Clamp scale factors to avoid extreme corrections
    scale_r = max(0.7, min(1.5, scale_r))
    scale_g = max(0.7, min(1.5, scale_g))
    scale_b = max(0.7, min(1.5, scale_b))

    r, g, b = img.split()
    r = r.point(lambda p: min(255, int(p * scale_r)))
    g = g.point(lambda p: min(255, int(p * scale_g)))
    b = b.point(lambda p: min(255, int(p * scale_b)))

    return Image.merge('RGB', (r, g, b))


def brand_tint(img, hex_color, intensity=0.08):
    """Apply subtle brand color tint to image.

    Creates a cohesive look by blending a semi-transparent color overlay.

    Args:
        img: PIL Image
        hex_color: Brand color as hex (#RRGGBB)
        intensity: Blend intensity 0.0-1.0 (default 0.08 = very subtle)

    Returns:
        Tinted PIL Image
    """
    img = img.convert('RGBA')
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)

    # Create color overlay
    overlay = Image.new('RGBA', img.size, (r, g, b, int(255 * intensity)))
    result = Image.alpha_composite(img, overlay)

    return result


def warm_tone(img, intensity=0.05):
    """Apply warm (golden hour) tone — adds subtle orange/amber."""
    return brand_tint(img, '#FFB347', intensity)


def cool_tone(img, intensity=0.05):
    """Apply cool (blue hour) tone — adds subtle blue."""
    return brand_tint(img, '#6CB4EE', intensity)


def process_image(image_path, output_path=None, hex_color=None, tone=None):
    """Full color correction pipeline for a single image.

    Args:
        image_path: Input image path
        output_path: Output path (default: overwrites original)
        hex_color: Brand color for tinting (optional)
        tone: 'warm', 'cool', or None

    Returns:
        Output path on success, None on failure
    """
    try:
        img = Image.open(image_path)

        # Step 1: White balance
        img = auto_white_balance(img)

        # Step 2: Auto enhance
        img = auto_enhance(img)

        # Step 3: Brand tint (very subtle)
        if hex_color:
            img = brand_tint(img, hex_color, intensity=0.06)

        # Step 4: Tone (optional)
        if tone == 'warm':
            img = warm_tone(img)
        elif tone == 'cool':
            img = cool_tone(img)

        # Save
        save_path = output_path or image_path
        if save_path.lower().endswith(('.jpg', '.jpeg')):
            img = img.convert('RGB')
            img.save(save_path, 'JPEG', quality=95)
        else:
            img.save(save_path, 'PNG')

        print(f"[ColorCorrection] Processed: {os.path.basename(save_path)}")
        return save_path

    except Exception as e:
        print(f"[ColorCorrection] Error: {e}")
        return None


def process_batch(image_paths, hex_color=None, tone=None):
    """Process multiple images with consistent color correction.

    Args:
        image_paths: List of image file paths
        hex_color: Brand color for tinting
        tone: 'warm', 'cool', or None

    Returns:
        List of processed paths
    """
    results = []
    for path in image_paths:
        result = process_image(path, hex_color=hex_color, tone=tone)
        results.append(result or path)
    print(f"[ColorCorrection] Batch done: {len(results)} images")
    return results

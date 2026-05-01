"""
Mr.Creative Smart Crop
Auto-crop images to target aspect ratios while keeping subject centered.
Uses rembg mask for subject detection, falls back to center crop.

Inspired by thumbor/thumbor — focal point cropping, face-aware resize.
"""

import os
from PIL import Image, ImageFilter, ImageStat


# Standard aspect ratio dimensions (width, height)
ASPECT_RATIOS = {
    '1:1': (1080, 1080),
    '4:5': (1080, 1350),
    '9:16': (1080, 1920),
    '16:9': (1920, 1080),
    '3:4': (1080, 1440),
    '2:3': (1080, 1620),
    '21:9': (2520, 1080),
}


def detect_subject_bbox(img):
    """Detect subject bounding box using edge detection.
    Returns (left, top, right, bottom) of the subject area."""
    gray = img.convert('L')

    # Edge detection
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edges = edges.filter(ImageFilter.GaussianBlur(radius=3))

    # Threshold to binary
    threshold = 30
    binary = edges.point(lambda p: 255 if p > threshold else 0)

    # Find bounding box of non-zero pixels
    bbox = binary.getbbox()
    if bbox:
        return bbox

    # Fallback: center 60% of image
    w, h = img.size
    margin_x = int(w * 0.2)
    margin_y = int(h * 0.2)
    return (margin_x, margin_y, w - margin_x, h - margin_y)


def detect_subject_with_rembg(img):
    """Use rembg to detect subject mask, then find bounding box.
    More accurate than edge detection for product photos."""
    try:
        from rembg import remove, new_session
        session = new_session('u2net')
        # Get mask only
        result = remove(img, session=session, only_mask=True, post_process_mask=True)
        bbox = result.getbbox()
        if bbox:
            # Add small padding (5%)
            w, h = img.size
            pad_x = int(w * 0.05)
            pad_y = int(h * 0.05)
            return (
                max(0, bbox[0] - pad_x),
                max(0, bbox[1] - pad_y),
                min(w, bbox[2] + pad_x),
                min(h, bbox[3] + pad_y),
            )
    except Exception as e:
        print(f"[SmartCrop] rembg detection failed, using edge detection: {e}")

    return detect_subject_bbox(img)


def smart_crop(img, target_ratio='1:1', target_size=None, use_rembg=False):
    """Crop image to target aspect ratio, keeping subject centered.

    Args:
        img: PIL Image
        target_ratio: Target aspect ratio string (e.g. '1:1', '16:9')
        target_size: Tuple (width, height) — overrides ratio lookup
        use_rembg: Use rembg for more accurate subject detection (slower)

    Returns:
        Cropped and resized PIL Image
    """
    if target_size:
        target_w, target_h = target_size
    elif target_ratio in ASPECT_RATIOS:
        target_w, target_h = ASPECT_RATIOS[target_ratio]
    else:
        # Parse ratio string
        parts = target_ratio.split(':')
        if len(parts) == 2:
            rw, rh = int(parts[0]), int(parts[1])
            target_w = 1080
            target_h = int(1080 * rh / rw)
        else:
            target_w, target_h = 1080, 1080

    src_w, src_h = img.size
    target_aspect = target_w / target_h
    src_aspect = src_w / src_h

    # Detect subject center
    if use_rembg:
        bbox = detect_subject_with_rembg(img)
    else:
        bbox = detect_subject_bbox(img)

    subject_cx = (bbox[0] + bbox[2]) // 2
    subject_cy = (bbox[1] + bbox[3]) // 2

    # Calculate crop region
    if src_aspect > target_aspect:
        # Source is wider — crop width
        crop_h = src_h
        crop_w = int(crop_h * target_aspect)
    else:
        # Source is taller — crop height
        crop_w = src_w
        crop_h = int(crop_w / target_aspect)

    # Center crop on subject
    left = max(0, min(subject_cx - crop_w // 2, src_w - crop_w))
    top = max(0, min(subject_cy - crop_h // 2, src_h - crop_h))

    # Crop and resize
    cropped = img.crop((left, top, left + crop_w, top + crop_h))
    result = cropped.resize((target_w, target_h), Image.LANCZOS)

    return result


def crop_to_all_ratios(image_path, output_dir, ratios=None, use_rembg=False):
    """Crop a single image to multiple aspect ratios.

    Args:
        image_path: Input image path
        output_dir: Directory to save cropped images
        ratios: List of ratio strings (default: all standard ratios)
        use_rembg: Use rembg for subject detection

    Returns:
        Dict of {ratio: output_path}
    """
    if ratios is None:
        ratios = ['1:1', '4:5', '9:16', '16:9']

    os.makedirs(output_dir, exist_ok=True)
    img = Image.open(image_path).convert('RGB')
    base = os.path.splitext(os.path.basename(image_path))[0]

    results = {}
    for ratio in ratios:
        cropped = smart_crop(img, target_ratio=ratio, use_rembg=use_rembg)
        safe_ratio = ratio.replace(':', 'x')
        out_path = os.path.join(output_dir, f'{base}_{safe_ratio}.png')
        cropped.save(out_path, 'PNG')
        results[ratio] = out_path
        print(f"[SmartCrop] {ratio} → {os.path.basename(out_path)}")

    return results


def batch_smart_crop(image_paths, target_ratio='1:1', output_dir=None, use_rembg=False):
    """Smart-crop multiple images to the same aspect ratio.

    Args:
        image_paths: List of image paths
        target_ratio: Target aspect ratio
        output_dir: Output directory (default: same dir as input)
        use_rembg: Use rembg for subject detection

    Returns:
        List of output paths
    """
    results = []
    for path in image_paths:
        img = Image.open(path).convert('RGB')
        cropped = smart_crop(img, target_ratio=target_ratio, use_rembg=use_rembg)

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            out = os.path.join(output_dir, os.path.basename(path))
        else:
            base, ext = os.path.splitext(path)
            out = f'{base}_cropped{ext}'

        cropped.save(out)
        results.append(out)

    print(f"[SmartCrop] Batch: {len(results)} images cropped to {target_ratio}")
    return results

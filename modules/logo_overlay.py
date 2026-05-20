"""Post-processor: overlay brand logo on generated images."""
import os
from PIL import Image


def apply_logo(image_path, logo_path, position='bottom-right', scale=0.15, padding=20):
    """Composite brand logo onto an image.

    Args:
        image_path: path to the generated image
        logo_path: path to logo file (relative to static/)
        position: bottom-right | bottom-left | top-right | top-left
        scale: logo width as fraction of image width (default 15%)
        padding: pixel padding from edges
    """
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')
    logo_full = os.path.join(static_dir, logo_path)

    if not os.path.exists(logo_full) or not os.path.exists(image_path):
        return False

    try:
        img = Image.open(image_path).convert('RGBA')
        logo = Image.open(logo_full).convert('RGBA')

        # Scale logo to fraction of image width
        logo_w = int(img.width * scale)
        logo_h = int(logo.height * (logo_w / logo.width))
        logo = logo.resize((logo_w, logo_h), Image.LANCZOS)

        # Calculate position
        if position == 'bottom-right':
            x = img.width - logo_w - padding
            y = img.height - logo_h - padding
        elif position == 'bottom-left':
            x = padding
            y = img.height - logo_h - padding
        elif position == 'top-right':
            x = img.width - logo_w - padding
            y = padding
        elif position == 'top-left':
            x = padding
            y = padding
        else:
            x = img.width - logo_w - padding
            y = img.height - logo_h - padding

        # Composite
        img.paste(logo, (x, y), logo)

        # Save back (convert to RGB if original was jpg)
        if image_path.lower().endswith(('.jpg', '.jpeg')):
            img = img.convert('RGB')
        img.save(image_path, quality=95)
        return True
    except Exception as e:
        print(f'[LogoOverlay] Error: {e}')
        return False

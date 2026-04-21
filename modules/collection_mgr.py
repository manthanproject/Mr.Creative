"""
Mr.Creative — Collection Manager
Handles: file organization, thumbnails, ZIP export, manual uploads.
"""

import os
import shutil
import zipfile
from datetime import datetime
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'mp4', 'webm', 'mov'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_file_type(filename):
    """Determine if file is image or video."""
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if ext in {'mp4', 'webm', 'mov', 'avi'}:
        return 'video'
    return 'image'


def save_upload_to_collection(file, collection_id, output_folder, user_id):
    """
    Save an uploaded file into a collection folder.

    Returns dict with file info or None on error.
    """
    if not file or not file.filename:
        return None

    if not allowed_file(file.filename):
        return None

    # Create collection folder
    col_dir = os.path.join(output_folder, f'collection_{collection_id}')
    os.makedirs(col_dir, exist_ok=True)

    # Generate unique filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    original_name = secure_filename(file.filename)
    filename = f"{timestamp}_{original_name}"
    filepath = os.path.join(col_dir, filename)

    file.save(filepath)

    # Get file size
    file_size = os.path.getsize(filepath)

    return {
        'filename': filename,
        'original_name': original_name,
        'path': f'outputs/collection_{collection_id}/{filename}',
        'full_path': filepath,
        'file_type': get_file_type(filename),
        'file_size': file_size,
        'collection_id': collection_id,
    }


def move_files_to_collection(file_paths, collection_id, output_folder):
    """
    Move downloaded files into a collection folder.

    Args:
        file_paths: list of absolute file paths
        collection_id: target collection ID
        output_folder: base output folder

    Returns list of new file info dicts.
    """
    col_dir = os.path.join(output_folder, f'collection_{collection_id}')
    os.makedirs(col_dir, exist_ok=True)

    moved = []
    for fp in file_paths:
        if not os.path.exists(fp):
            continue

        filename = os.path.basename(fp)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        new_name = f"{timestamp}_{filename}"
        dest = os.path.join(col_dir, new_name)

        shutil.move(fp, dest)

        moved.append({
            'filename': new_name,
            'original_name': filename,
            'path': os.path.join('outputs', f'collection_{collection_id}', new_name),
            'full_path': dest,
            'file_type': get_file_type(filename),
            'file_size': os.path.getsize(dest),
        })

    return moved


def export_collection_as_zip(collection_id, output_folder, generations):
    """
    Export all files in a collection as a ZIP.

    Args:
        collection_id: collection ID
        output_folder: base output folder
        generations: list of Generation objects with output_path

    Returns path to ZIP file or None.
    """
    col_dir = os.path.join(output_folder, f'collection_{collection_id}')
    zip_dir = os.path.join(output_folder, 'exports')
    os.makedirs(zip_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    zip_name = f"collection_{collection_id}_{timestamp}.zip"
    zip_path = os.path.join(zip_dir, zip_name)

    file_count = 0

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add files from collection folder
        if os.path.exists(col_dir):
            for f in os.listdir(col_dir):
                fp = os.path.join(col_dir, f)
                if os.path.isfile(fp):
                    zf.write(fp, f)
                    file_count += 1

        # Add files from generation records
        for gen in generations:
            if gen.output_path:
                fp = os.path.join(output_folder, '..', gen.output_path)
                if os.path.exists(fp):
                    zf.write(fp, os.path.basename(fp))
                    file_count += 1

    if file_count == 0:
        os.remove(zip_path)
        return None

    return os.path.join('outputs', 'exports', zip_name)


def get_collection_files(collection_id, output_folder):
    """
    Get all files in a collection folder.

    Returns list of file info dicts.
    """
    col_dir = os.path.join(output_folder, f'collection_{collection_id}')
    files = []

    if not os.path.exists(col_dir):
        return files

    for f in sorted(os.listdir(col_dir), reverse=True):
        fp = os.path.join(col_dir, f)
        if os.path.isfile(fp):
            files.append({
                'filename': f,
                'path': f'outputs/collection_{collection_id}/{f}',
                'file_type': get_file_type(f),
                'file_size': os.path.getsize(fp),
                'modified': datetime.fromtimestamp(os.path.getmtime(fp)),
            })

    return files

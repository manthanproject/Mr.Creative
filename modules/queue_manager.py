"""
Mr.Creative — Queue Manager
Processes generation jobs sequentially using the Selenium bot.
"""

import os
import shutil
import threading
from datetime import datetime
from typing import Any


class QueueManager:
    """Manages the job queue and processes them with the Selenium bot."""

    def __init__(self, app):
        self.app = app
        self.is_processing = False
        self.current_job: Any = None
        self._lock = threading.Lock()

    def process_next_job(self):
        """Process the next queued job."""
        from models import db, JobQueue, Generation, Prompt
        from modules.selenium_bot import PomelliBot

        with self._lock:
            if self.is_processing:
                return  # Already processing
            self.is_processing = True

        try:
            with self.app.app_context():
                # Get next queued job
                job = JobQueue.query.filter_by(status='queued')\
                    .order_by(JobQueue.priority.desc(), JobQueue.created_at.asc())\
                    .first()

                if not job:
                    return

                # Mark as processing
                job.status = 'processing'
                job.started_at = datetime.utcnow()
                db.session.commit()
                self.current_job = job

                # Get associated prompt
                prompt = Prompt.query.get(job.prompt_id) if job.prompt_id else None
                prompt_text = prompt.text if prompt else ''

                # Get associated generation
                generation = Generation.query.get(job.generation_id) if job.generation_id else None

                # Setup bot config
                config = {
                    'google_email': self.app.config.get('GOOGLE_EMAIL', ''),
                    'google_password': self.app.config.get('GOOGLE_PASSWORD', ''),
                    'download_dir': self.app.config.get('DOWNLOAD_DIR', 'static/downloads'),
                    'headless': self.app.config.get('HEADLESS_MODE', False),
                    'chrome_profile_dir': os.path.join(
                        self.app.instance_path, 'chrome_profile'
                    ),
                }

                # Run the bot
                bot = PomelliBot(config)
                image_path = generation.input_image_path if generation else None
                animate = job.job_type == 'animate'

                result = bot.run_full_workflow(
                    prompt_text=prompt_text,
                    image_path=image_path,
                    animate=animate,
                )

                # Process results
                if result['success']:
                    job.status = 'completed'
                    job.completed_at = datetime.utcnow()

                    # Move downloaded files to outputs
                    output_dir = self.app.config.get('OUTPUT_FOLDER', 'static/outputs')
                    os.makedirs(output_dir, exist_ok=True)

                    for filepath in result.get('downloaded_files', []):
                        if os.path.exists(filepath):
                            filename = os.path.basename(filepath)
                            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                            new_name = f"{timestamp}_{filename}"
                            dest = os.path.join(output_dir, new_name)
                            shutil.move(filepath, dest)

                            # Update generation record
                            if generation:
                                generation.output_path = os.path.join('outputs', new_name)
                                generation.status = 'completed'
                                generation.completed_at = datetime.utcnow()

                    # Update prompt status
                    if prompt:
                        prompt.status = 'completed'

                else:
                    job.status = 'failed'
                    job.error_message = '; '.join(result.get('errors', ['Unknown error']))
                    job.retry_count += 1

                    if generation:
                        generation.status = 'failed'
                        generation.error_message = job.error_message

                    if prompt:
                        prompt.status = 'failed'

                db.session.commit()

        except Exception as e:
            with self.app.app_context():
                if self.current_job:
                    self.current_job.status = 'failed'
                    self.current_job.error_message = str(e)
                    db.session.commit()

        finally:
            self.is_processing = False
            self.current_job = None

    def start_processing(self):
        """Start processing in a background thread."""
        thread = threading.Thread(target=self.process_next_job, daemon=True)
        thread.start()
        return thread

    def get_status(self):
        """Get current queue status."""
        from models import JobQueue
        with self.app.app_context():
            return {
                'is_processing': self.is_processing,
                'queued': JobQueue.query.filter_by(status='queued').count(),
                'processing': JobQueue.query.filter_by(status='processing').count(),
                'completed': JobQueue.query.filter_by(status='completed').count(),
                'failed': JobQueue.query.filter_by(status='failed').count(),
            }

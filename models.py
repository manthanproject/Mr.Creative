from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import uuid

db = SQLAlchemy()


def generate_uuid():
    return str(uuid.uuid4())


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    avatar_color = db.Column(db.String(7), default='#6C5CE7')
    created_at = db.Column(db.DateTime, default=datetime.now)
    last_login = db.Column(db.DateTime, default=datetime.now)

    # Relationships
    projects = db.relationship('Project', backref='owner', lazy='dynamic', cascade='all, delete-orphan')
    prompts = db.relationship('Prompt', backref='owner', lazy='dynamic', cascade='all, delete-orphan')
    generations = db.relationship('Generation', backref='owner', lazy='dynamic', cascade='all, delete-orphan')
    collections = db.relationship('Collection', backref='owner', lazy='dynamic', cascade='all, delete-orphan')
    scheduled_jobs = db.relationship('ScheduledJob', backref='owner', lazy='dynamic', cascade='all, delete-orphan')
    social_posts = db.relationship('SocialPost', backref='owner', lazy='dynamic', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def initials(self):
        return self.username[:2].upper()


class Project(db.Model):
    __tablename__ = 'projects'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    website_url = db.Column(db.String(500), default='')
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    prompts = db.relationship('Prompt', backref='project', lazy='dynamic', cascade='all, delete-orphan')
    generations = db.relationship('Generation', backref='project', lazy='dynamic', cascade='all, delete-orphan')


class Prompt(db.Model):
    __tablename__ = 'prompts'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    project_id = db.Column(db.String(36), db.ForeignKey('projects.id'), nullable=True)
    text = db.Column(db.Text, nullable=False)
    prompt_type = db.Column(db.String(20), default='manual')  # manual, generated, edited
    source_prompt_id = db.Column(db.String(36), nullable=True)  # If generated from another prompt
    is_favorite = db.Column(db.Boolean, default=False)
    is_approved = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='draft')  # draft, approved, queued, processing, completed, failed
    created_at = db.Column(db.DateTime, default=datetime.now)

    # Relationships
    generations = db.relationship('Generation', backref='prompt', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'text': self.text,
            'prompt_type': self.prompt_type,
            'is_favorite': self.is_favorite,
            'is_approved': self.is_approved,
            'status': self.status,
            'created_at': self.created_at.isoformat(),
        }


class Generation(db.Model):
    __tablename__ = 'generations'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    project_id = db.Column(db.String(36), db.ForeignKey('projects.id'), nullable=True)
    prompt_id = db.Column(db.String(36), db.ForeignKey('prompts.id'), nullable=True)
    collection_id = db.Column(db.String(36), db.ForeignKey('collections.id'), nullable=True)

    # Input
    input_type = db.Column(db.String(20), default='text')  # text, image, both
    input_image_path = db.Column(db.String(500), nullable=True)

    # Output
    output_type = db.Column(db.String(20), default='image')  # image, video
    output_path = db.Column(db.String(500), nullable=True)
    thumbnail_path = db.Column(db.String(500), nullable=True)
    pomelli_feature = db.Column(db.String(30), default='campaign')  # campaign, photoshoot, animate

    # Status
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed, downloading
    error_message = db.Column(db.Text, nullable=True)

    # Metadata
    file_size = db.Column(db.Integer, default=0)
    width = db.Column(db.Integer, nullable=True)
    height = db.Column(db.Integer, nullable=True)
    duration = db.Column(db.Float, nullable=True)  # For videos, in seconds
    tags = db.Column(db.Text, default='')  # Comma-separated tags

    created_at = db.Column(db.DateTime, default=datetime.now)
    completed_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'input_type': self.input_type,
            'output_type': self.output_type,
            'output_path': self.output_path,
            'thumbnail_path': self.thumbnail_path,
            'pomelli_feature': self.pomelli_feature,
            'status': self.status,
            'created_at': self.created_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }


class Collection(db.Model):
    __tablename__ = 'collections'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    cover_image_path = db.Column(db.String(500), nullable=True)
    is_public = db.Column(db.Boolean, default=False)
    share_token = db.Column(db.String(36), default=generate_uuid, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    generations = db.relationship('Generation', backref='collection', lazy='dynamic')

    @property
    def item_count(self):
        """Fresh DB query — avoids stale lazy relationship counts."""
        return Generation.query.filter_by(collection_id=self.id, status='completed').count()

    @property
    def cover_image(self):
        """Auto-pick cover from first image if no custom cover is set."""
        if self.cover_image_path:
            return self.cover_image_path
        first = Generation.query.filter_by(
            collection_id=self.id, output_type='image', status='completed'
        ).order_by(Generation.created_at.asc()).first()
        return first.output_path if first else None

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'cover_image_path': self.cover_image,
            'is_public': self.is_public,
            'share_token': self.share_token,
            'item_count': self.item_count,
            'created_at': self.created_at.isoformat(),
        }


class ScheduledJob(db.Model):
    __tablename__ = 'scheduled_jobs'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    prompt_text = db.Column(db.Text, nullable=False)
    pomelli_feature = db.Column(db.String(30), default='campaign')
    schedule_type = db.Column(db.String(20), default='once')  # once, daily, weekly
    scheduled_time = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    last_run = db.Column(db.DateTime, nullable=True)
    next_run = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    # Photoshoot/Generate support
    image_path = db.Column(db.String(500), nullable=True)      # Uploaded product image path
    templates = db.Column(db.Text, default='[]')                # JSON array of template names
    aspect_ratio = db.Column(db.String(20), default='story')    # story, square, feed
    product_url = db.Column(db.String(500), nullable=True)      # Campaign product URL


class JobQueue(db.Model):
    __tablename__ = 'job_queue'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    prompt_id = db.Column(db.String(36), db.ForeignKey('prompts.id'), nullable=True)
    generation_id = db.Column(db.String(36), db.ForeignKey('generations.id'), nullable=True)
    job_type = db.Column(db.String(30), default='generate')  # generate, animate, photoshoot
    status = db.Column(db.String(20), default='queued')  # queued, processing, completed, failed
    priority = db.Column(db.Integer, default=0)
    retry_count = db.Column(db.Integer, default=0)
    max_retries = db.Column(db.Integer, default=3)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)


class SocialPost(db.Model):
    __tablename__ = 'social_posts'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    collection_id = db.Column(db.String(36), db.ForeignKey('collections.id'), nullable=True)

    # Platform
    platform = db.Column(db.String(20), default='pinterest')  # pinterest, instagram, facebook

    # Content
    image_path = db.Column(db.String(500), nullable=False)
    title = db.Column(db.String(200), default='')
    caption = db.Column(db.Text, default='')
    hashtags = db.Column(db.Text, default='')
    pin_link = db.Column(db.String(500), default='')
    board_id = db.Column(db.String(100), default='')
    board_name = db.Column(db.String(200), default='')

    # Schedule
    scheduled_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='draft')  # draft, scheduled, posting, posted, failed
    posted_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    platform_post_id = db.Column(db.String(100), nullable=True)
    platform_post_url = db.Column(db.String(500), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
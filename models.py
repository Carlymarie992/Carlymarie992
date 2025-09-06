from datetime import datetime
from app import db
from werkzeug.security import generate_password_hash, check_password_hash
import hashlib
import json


class User(db.Model):
    """User model for authentication and access control"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default='user')  # user, admin, forensic_analyst
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Relationships
    documents = db.relationship('Document', backref='owner', lazy=True)
    audit_logs = db.relationship('AuditLog', backref='user', lazy=True)
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check password against hash"""
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        """Convert user to dictionary (exclude sensitive data)"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }


class Document(db.Model):
    """Document model for file management"""
    __tablename__ = 'documents'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    file_type = db.Column(db.String(50), nullable=False)
    content_hash = db.Column(db.String(64), nullable=False)  # SHA256 hash
    encryption_key = db.Column(db.String(255))  # Encrypted storage key
    
    # Metadata
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    case_number = db.Column(db.String(100))
    tags = db.Column(db.Text)  # JSON string of tags
    description = db.Column(db.Text)
    
    # Processing status
    is_processed = db.Column(db.Boolean, default=False)
    processing_status = db.Column(db.String(50), default='pending')  # pending, processing, completed, error
    
    # Relationships
    summaries = db.relationship('DocumentSummary', backref='document', lazy=True)
    redactions = db.relationship('DocumentRedaction', backref='document', lazy=True)
    timelines = db.relationship('DocumentTimeline', backref='document', lazy=True)
    
    def calculate_hash(self, file_content):
        """Calculate SHA256 hash of file content"""
        return hashlib.sha256(file_content).hexdigest()
    
    def verify_integrity(self, file_content):
        """Verify file integrity using hash"""
        return self.content_hash == self.calculate_hash(file_content)
    
    def to_dict(self):
        """Convert document to dictionary"""
        return {
            'id': self.id,
            'filename': self.filename,
            'original_filename': self.original_filename,
            'file_size': self.file_size,
            'file_type': self.file_type,
            'content_hash': self.content_hash,
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None,
            'user_id': self.user_id,
            'case_number': self.case_number,
            'tags': json.loads(self.tags) if self.tags else [],
            'description': self.description,
            'is_processed': self.is_processed,
            'processing_status': self.processing_status
        }


class DocumentSummary(db.Model):
    """Document summary storage"""
    __tablename__ = 'document_summaries'
    
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    summary_type = db.Column(db.String(50), nullable=False)  # brief, detailed, key_points
    content = db.Column(db.Text, nullable=False)
    confidence_score = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processing_time = db.Column(db.Float)  # seconds
    
    def to_dict(self):
        return {
            'id': self.id,
            'document_id': self.document_id,
            'summary_type': self.summary_type,
            'content': self.content,
            'confidence_score': self.confidence_score,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'processing_time': self.processing_time
        }


class DocumentRedaction(db.Model):
    """Document redaction information"""
    __tablename__ = 'document_redactions'
    
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    redaction_type = db.Column(db.String(50), nullable=False)  # pii, sensitive, custom
    start_position = db.Column(db.Integer)
    end_position = db.Column(db.Integer)
    original_text = db.Column(db.Text)  # Encrypted
    redacted_text = db.Column(db.Text)
    reason = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    applied_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    def to_dict(self):
        return {
            'id': self.id,
            'document_id': self.document_id,
            'redaction_type': self.redaction_type,
            'start_position': self.start_position,
            'end_position': self.end_position,
            'redacted_text': self.redacted_text,
            'reason': self.reason,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'applied_by': self.applied_by
        }


class DocumentTimeline(db.Model):
    """Document timeline events"""
    __tablename__ = 'document_timelines'
    
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    event_date = db.Column(db.DateTime, nullable=False)
    event_type = db.Column(db.String(100), nullable=False)
    event_description = db.Column(db.Text, nullable=False)
    page_number = db.Column(db.Integer)
    confidence_score = db.Column(db.Float)
    extracted_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'document_id': self.document_id,
            'event_date': self.event_date.isoformat() if self.event_date else None,
            'event_type': self.event_type,
            'event_description': self.event_description,
            'page_number': self.page_number,
            'confidence_score': self.confidence_score,
            'extracted_at': self.extracted_at.isoformat() if self.extracted_at else None
        }


class AuditLog(db.Model):
    """Comprehensive audit logging for forensic purposes"""
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(db.String(100), nullable=False)
    resource_type = db.Column(db.String(50), nullable=False)  # document, user, system
    resource_id = db.Column(db.String(50))
    details = db.Column(db.Text)  # JSON details
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    session_id = db.Column(db.String(255))
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'action': self.action,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id,
            'details': json.loads(self.details) if self.details else {},
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'session_id': self.session_id
        }


class ChatAnalysis(db.Model):
    """Chat prompt analysis and logging"""
    __tablename__ = 'chat_analyses'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    chat_content = db.Column(db.Text, nullable=False)
    analysis_result = db.Column(db.Text)  # AI analysis result
    sentiment_score = db.Column(db.Float)
    keywords = db.Column(db.Text)  # JSON array of keywords
    entities = db.Column(db.Text)  # JSON array of entities
    content_hash = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processing_time = db.Column(db.Float)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'analysis_result': self.analysis_result,
            'sentiment_score': self.sentiment_score,
            'keywords': json.loads(self.keywords) if self.keywords else [],
            'entities': json.loads(self.entities) if self.entities else [],
            'content_hash': self.content_hash,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'processing_time': self.processing_time
        }
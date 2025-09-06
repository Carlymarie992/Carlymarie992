import os
import re
import hashlib
import json
from datetime import datetime
from flask import request
from models import AuditLog
from app import db
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def validate_password_strength(password):
    """
    Validate password strength requirements
    - At least 8 characters
    - Contains uppercase letter
    - Contains lowercase letter
    - Contains number
    - Contains special character
    """
    if len(password) < 8:
        return False
    
    if not re.search(r'[A-Z]', password):
        return False
    
    if not re.search(r'[a-z]', password):
        return False
    
    if not re.search(r'\d', password):
        return False
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False
    
    return True


def log_audit_event(action, resource_type, resource_id=None, user_id=None, details=None):
    """
    Log audit event for forensic purposes
    """
    try:
        # Get request context information
        ip_address = request.remote_addr if request else None
        user_agent = request.headers.get('User-Agent') if request else None
        session_id = request.headers.get('X-Session-ID') if request else None
        
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=json.dumps(details) if details else None,
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
            timestamp=datetime.utcnow()
        )
        
        db.session.add(audit_log)
        db.session.commit()
        
        # Also log to file for backup
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'user_id': user_id,
            'action': action,
            'resource_type': resource_type,
            'resource_id': resource_id,
            'details': details,
            'ip_address': ip_address,
            'user_agent': user_agent,
            'session_id': session_id
        }
        
        logger.info(f"AUDIT: {json.dumps(log_entry)}")
        
    except Exception as e:
        logger.error(f"Failed to log audit event: {str(e)}")
        # Continue execution even if logging fails


def calculate_file_hash(file_content, algorithm='sha256'):
    """
    Calculate hash of file content for integrity verification
    """
    if algorithm.lower() == 'sha256':
        return hashlib.sha256(file_content).hexdigest()
    elif algorithm.lower() == 'md5':
        return hashlib.md5(file_content).hexdigest()
    else:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")


def allowed_file(filename, allowed_extensions=None):
    """
    Check if file extension is allowed
    """
    if allowed_extensions is None:
        allowed_extensions = {
            'pdf', 'doc', 'docx', 'txt', 'rtf',
            'mp3', 'wav', 'mp4', 'avi', 'mov',
            'jpg', 'jpeg', 'png', 'tiff', 'bmp',
            'xls', 'xlsx', 'csv'
        }
    
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions


def sanitize_filename(filename):
    """
    Sanitize filename to prevent directory traversal and other attacks
    """
    # Remove path components
    filename = os.path.basename(filename)
    
    # Remove or replace dangerous characters
    filename = re.sub(r'[^\w\s.-]', '_', filename)
    
    # Limit length
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255-len(ext)] + ext
    
    return filename


def get_file_type(filename):
    """
    Determine file type category based on extension
    """
    ext = filename.lower().split('.')[-1] if '.' in filename else ''
    
    if ext in ['pdf', 'doc', 'docx', 'txt', 'rtf']:
        return 'document'
    elif ext in ['mp3', 'wav', 'flac', 'aac']:
        return 'audio'
    elif ext in ['mp4', 'avi', 'mov', 'wmv', 'mkv']:
        return 'video'
    elif ext in ['jpg', 'jpeg', 'png', 'gif', 'tiff', 'bmp']:
        return 'image'
    elif ext in ['xls', 'xlsx', 'csv']:
        return 'spreadsheet'
    else:
        return 'other'


def format_file_size(size_bytes):
    """
    Format file size in human readable format
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.2f} {size_names[i]}"


def redact_text(text, redaction_type='***REDACTED***'):
    """
    Basic text redaction utility
    """
    if not text:
        return text
    
    # Common patterns to redact
    patterns = {
        'ssn': r'\b\d{3}-\d{2}-\d{4}\b',
        'phone': r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
        'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'credit_card': r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'
    }
    
    redacted_text = text
    redactions_made = []
    
    for pattern_name, pattern in patterns.items():
        matches = re.finditer(pattern, redacted_text)
        for match in matches:
            redactions_made.append({
                'type': pattern_name,
                'original': match.group(),
                'start': match.start(),
                'end': match.end()
            })
            redacted_text = redacted_text.replace(match.group(), redaction_type)
    
    return redacted_text, redactions_made


def extract_keywords(text, min_length=3):
    """
    Extract keywords from text (basic implementation)
    """
    if not text:
        return []
    
    # Remove common stop words
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during',
        'before', 'after', 'above', 'below', 'under', 'between', 'is', 'are',
        'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does',
        'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can',
        'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they'
    }
    
    # Extract words
    words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
    
    # Filter words
    keywords = [
        word for word in words 
        if len(word) >= min_length and word not in stop_words
    ]
    
    # Count frequency and return top keywords
    from collections import Counter
    word_counts = Counter(keywords)
    
    return [word for word, count in word_counts.most_common(20)]


def validate_json_structure(data, required_fields):
    """
    Validate JSON data structure
    """
    if not isinstance(data, dict):
        return False, "Data must be a JSON object"
    
    for field in required_fields:
        if field not in data:
            return False, f"Required field '{field}' is missing"
    
    return True, "Valid"


def create_chain_of_custody_record(document_id, action, user_id, details=None):
    """
    Create a chain of custody record for evidence integrity
    """
    record = {
        'document_id': document_id,
        'action': action,
        'user_id': user_id,
        'timestamp': datetime.utcnow().isoformat(),
        'details': details or {}
    }
    
    # Log as audit event
    log_audit_event(
        action=f'chain_of_custody_{action}',
        resource_type='document',
        resource_id=str(document_id),
        user_id=user_id,
        details=record
    )
    
    return record
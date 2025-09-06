from flask import Blueprint, request, jsonify, send_file, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
import os
import uuid
from datetime import datetime
from models import Document, User
from app import db, limiter
from utils.helpers import (
    log_audit_event, calculate_file_hash, allowed_file, 
    sanitize_filename, get_file_type, format_file_size,
    create_chain_of_custody_record
)

documents_bp = Blueprint('documents', __name__)


@documents_bp.route('/upload', methods=['POST'])
@jwt_required()
@limiter.limit("10 per minute")
def upload_document():
    """Upload a document with security validation"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Check if file is in request
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Validate file
        if not allowed_file(file.filename):
            return jsonify({'error': 'File type not allowed'}), 400
        
        # Get additional metadata
        case_number = request.form.get('case_number', '')
        description = request.form.get('description', '')
        tags = request.form.get('tags', '[]')  # JSON string
        
        # Read file content for processing
        file.seek(0)
        file_content = file.read()
        file.seek(0)
        
        # Validate file size
        file_size = len(file_content)
        if file_size > current_app.config['MAX_CONTENT_LENGTH']:
            return jsonify({
                'error': f'File too large. Maximum size: {format_file_size(current_app.config["MAX_CONTENT_LENGTH"])}'
            }), 400
        
        # Calculate file hash for integrity
        content_hash = calculate_file_hash(file_content)
        
        # Check for duplicate files
        existing_doc = Document.query.filter_by(content_hash=content_hash).first()
        if existing_doc:
            return jsonify({
                'error': 'File already exists',
                'existing_document_id': existing_doc.id
            }), 409
        
        # Generate secure filename
        original_filename = file.filename
        sanitized_name = sanitize_filename(original_filename)
        unique_filename = f"{uuid.uuid4()}_{sanitized_name}"
        
        # Create upload directory if it doesn't exist
        upload_dir = current_app.config['SECURE_UPLOAD_FOLDER']
        os.makedirs(upload_dir, exist_ok=True)
        
        # Save file
        file_path = os.path.join(upload_dir, unique_filename)
        file.save(file_path)
        
        # Create document record
        document = Document(
            filename=unique_filename,
            original_filename=original_filename,
            file_path=file_path,
            file_size=file_size,
            file_type=get_file_type(original_filename),
            content_hash=content_hash,
            user_id=user_id,
            case_number=case_number,
            description=description,
            tags=tags
        )
        
        db.session.add(document)
        db.session.commit()
        
        # Create chain of custody record
        create_chain_of_custody_record(
            document_id=document.id,
            action='uploaded',
            user_id=user_id,
            details={
                'original_filename': original_filename,
                'file_size': file_size,
                'content_hash': content_hash
            }
        )
        
        # Log upload
        log_audit_event(
            user_id=user_id,
            action='document_uploaded',
            resource_type='document',
            resource_id=str(document.id),
            details={
                'filename': original_filename,
                'file_size': file_size,
                'file_type': document.file_type,
                'case_number': case_number
            }
        )
        
        return jsonify({
            'message': 'Document uploaded successfully',
            'document': document.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        # Clean up file if it was saved
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        
        return jsonify({'error': 'Upload failed', 'details': str(e)}), 500


@documents_bp.route('', methods=['GET'])
@jwt_required()
def list_documents():
    """List user's documents with pagination and filtering"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        
        # Filter parameters
        case_number = request.args.get('case_number')
        file_type = request.args.get('file_type')
        search = request.args.get('search')
        
        # Build query
        query = Document.query.filter_by(user_id=user_id)
        
        if case_number:
            query = query.filter(Document.case_number.ilike(f'%{case_number}%'))
        
        if file_type:
            query = query.filter_by(file_type=file_type)
        
        if search:
            query = query.filter(
                db.or_(
                    Document.original_filename.ilike(f'%{search}%'),
                    Document.description.ilike(f'%{search}%')
                )
            )
        
        # Order by upload date (newest first)
        query = query.order_by(Document.uploaded_at.desc())
        
        # Paginate
        documents = query.paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return jsonify({
            'documents': [doc.to_dict() for doc in documents.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': documents.total,
                'pages': documents.pages,
                'has_next': documents.has_next,
                'has_prev': documents.has_prev
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to list documents', 'details': str(e)}), 500


@documents_bp.route('/<int:document_id>', methods=['GET'])
@jwt_required()
def get_document(document_id):
    """Get document details"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get document
        document = Document.query.filter_by(id=document_id, user_id=user_id).first()
        
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        # Log access
        log_audit_event(
            user_id=user_id,
            action='document_accessed',
            resource_type='document',
            resource_id=str(document_id),
            details={'filename': document.original_filename}
        )
        
        return jsonify({'document': document.to_dict()}), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get document', 'details': str(e)}), 500


@documents_bp.route('/<int:document_id>/download', methods=['GET'])
@jwt_required()
def download_document(document_id):
    """Download document file"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get document
        document = Document.query.filter_by(id=document_id, user_id=user_id).first()
        
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        # Check if file exists
        if not os.path.exists(document.file_path):
            return jsonify({'error': 'Document file not found on disk'}), 404
        
        # Verify file integrity
        with open(document.file_path, 'rb') as f:
            file_content = f.read()
        
        if not document.verify_integrity(file_content):
            # Log integrity violation
            log_audit_event(
                user_id=user_id,
                action='document_integrity_violation',
                resource_type='document',
                resource_id=str(document_id),
                details={
                    'filename': document.original_filename,
                    'expected_hash': document.content_hash,
                    'actual_hash': calculate_file_hash(file_content)
                }
            )
            return jsonify({'error': 'Document integrity check failed'}), 500
        
        # Create chain of custody record
        create_chain_of_custody_record(
            document_id=document.id,
            action='downloaded',
            user_id=user_id,
            details={'filename': document.original_filename}
        )
        
        # Log download
        log_audit_event(
            user_id=user_id,
            action='document_downloaded',
            resource_type='document',
            resource_id=str(document_id),
            details={'filename': document.original_filename}
        )
        
        return send_file(
            document.file_path,
            as_attachment=True,
            download_name=document.original_filename
        )
        
    except Exception as e:
        return jsonify({'error': 'Download failed', 'details': str(e)}), 500


@documents_bp.route('/<int:document_id>', methods=['PUT'])
@jwt_required()
def update_document(document_id):
    """Update document metadata"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get document
        document = Document.query.filter_by(id=document_id, user_id=user_id).first()
        
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        data = request.get_json()
        
        # Update allowed fields
        if 'case_number' in data:
            document.case_number = data['case_number']
        
        if 'description' in data:
            document.description = data['description']
        
        if 'tags' in data:
            document.tags = data['tags']
        
        db.session.commit()
        
        # Log update
        log_audit_event(
            user_id=user_id,
            action='document_updated',
            resource_type='document',
            resource_id=str(document_id),
            details={
                'filename': document.original_filename,
                'updated_fields': list(data.keys())
            }
        )
        
        return jsonify({
            'message': 'Document updated successfully',
            'document': document.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Update failed', 'details': str(e)}), 500


@documents_bp.route('/<int:document_id>', methods=['DELETE'])
@jwt_required()
@limiter.limit("5 per minute")
def delete_document(document_id):
    """Delete document (soft delete with audit trail)"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.role not in ['admin', 'forensic_analyst']:
            return jsonify({'error': 'Insufficient permissions'}), 403
        
        # Get document
        document = Document.query.filter_by(id=document_id, user_id=user_id).first()
        
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        # Store document info for logging
        doc_info = document.to_dict()
        
        # Create final chain of custody record
        create_chain_of_custody_record(
            document_id=document.id,
            action='deleted',
            user_id=user_id,
            details={'filename': document.original_filename}
        )
        
        # Log deletion
        log_audit_event(
            user_id=user_id,
            action='document_deleted',
            resource_type='document',
            resource_id=str(document_id),
            details=doc_info
        )
        
        # Remove file from disk
        if os.path.exists(document.file_path):
            os.remove(document.file_path)
        
        # Remove from database
        db.session.delete(document)
        db.session.commit()
        
        return jsonify({'message': 'Document deleted successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Deletion failed', 'details': str(e)}), 500


@documents_bp.route('/<int:document_id>/verify', methods=['POST'])
@jwt_required()
def verify_document_integrity(document_id):
    """Verify document integrity using hash comparison"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get document
        document = Document.query.filter_by(id=document_id, user_id=user_id).first()
        
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        # Check if file exists
        if not os.path.exists(document.file_path):
            return jsonify({
                'verified': False,
                'error': 'Document file not found on disk'
            }), 404
        
        # Read file and calculate hash
        with open(document.file_path, 'rb') as f:
            file_content = f.read()
        
        current_hash = calculate_file_hash(file_content)
        is_verified = current_hash == document.content_hash
        
        # Log verification
        log_audit_event(
            user_id=user_id,
            action='document_integrity_verified',
            resource_type='document',
            resource_id=str(document_id),
            details={
                'filename': document.original_filename,
                'verified': is_verified,
                'original_hash': document.content_hash,
                'current_hash': current_hash
            }
        )
        
        return jsonify({
            'verified': is_verified,
            'original_hash': document.content_hash,
            'current_hash': current_hash,
            'file_size': document.file_size,
            'last_modified': datetime.fromtimestamp(
                os.path.getmtime(document.file_path)
            ).isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Verification failed', 'details': str(e)}), 500
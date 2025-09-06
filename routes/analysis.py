from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import hashlib
import json
import time
from datetime import datetime, timedelta
from models import User, AuditLog, ChatAnalysis, Document
from app import db, limiter
from utils.helpers import log_audit_event, extract_keywords, calculate_file_hash

analysis_bp = Blueprint('analysis', __name__)


def analyze_chat_content_basic(content):
    """
    Basic chat content analysis (placeholder for AI integration)
    In production, integrate with sentiment analysis, NER, and other NLP services
    """
    analysis_result = {
        'sentiment': 'neutral',
        'sentiment_score': 0.0,
        'entities': [],
        'keywords': [],
        'topics': [],
        'urgency_level': 'low',
        'contains_sensitive_info': False
    }
    
    # Basic sentiment analysis
    positive_words = ['good', 'excellent', 'positive', 'success', 'agree', 'satisfied', 'happy']
    negative_words = ['bad', 'terrible', 'negative', 'failure', 'disagree', 'unsatisfied', 'angry', 'problem']
    
    content_lower = content.lower()
    positive_count = sum(1 for word in positive_words if word in content_lower)
    negative_count = sum(1 for word in negative_words if word in content_lower)
    
    if positive_count > negative_count:
        analysis_result['sentiment'] = 'positive'
        analysis_result['sentiment_score'] = min(0.8, (positive_count - negative_count) * 0.2)
    elif negative_count > positive_count:
        analysis_result['sentiment'] = 'negative'
        analysis_result['sentiment_score'] = max(-0.8, (positive_count - negative_count) * 0.2)
    
    # Extract keywords
    analysis_result['keywords'] = extract_keywords(content)[:10]
    
    # Basic entity detection (placeholder)
    import re
    
    # Email addresses
    emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', content)
    for email in emails:
        analysis_result['entities'].append({'type': 'email', 'value': email})
    
    # Phone numbers
    phones = re.findall(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', content)
    for phone in phones:
        analysis_result['entities'].append({'type': 'phone', 'value': phone})
    
    # Dates
    dates = re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', content)
    for date in dates:
        analysis_result['entities'].append({'type': 'date', 'value': date})
    
    # Check for sensitive information
    sensitive_patterns = [
        r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
        r'\b\d{16}\b',  # Credit card
        r'\bpassword\b',
        r'\bconfidential\b'
    ]
    
    for pattern in sensitive_patterns:
        if re.search(pattern, content_lower):
            analysis_result['contains_sensitive_info'] = True
            break
    
    # Determine urgency
    urgent_keywords = ['urgent', 'emergency', 'asap', 'immediately', 'critical', 'deadline']
    if any(keyword in content_lower for keyword in urgent_keywords):
        analysis_result['urgency_level'] = 'high'
    elif any(keyword in content_lower for keyword in ['soon', 'priority', 'important']):
        analysis_result['urgency_level'] = 'medium'
    
    return analysis_result


@analysis_bp.route('/chat', methods=['POST'])
@jwt_required()
@limiter.limit("20 per minute")
def analyze_chat():
    """Analyze chat prompt for content, sentiment, and security"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        
        if not data or 'content' not in data:
            return jsonify({'error': 'Chat content is required'}), 400
        
        chat_content = data['content']
        
        if len(chat_content.strip()) < 5:
            return jsonify({'error': 'Chat content too short for analysis'}), 400
        
        if len(chat_content) > 10000:
            return jsonify({'error': 'Chat content too long (max 10,000 characters)'}), 400
        
        start_time = time.time()
        
        # Calculate content hash for deduplication
        content_hash = calculate_file_hash(chat_content.encode('utf-8'))
        
        # Check if this content was already analyzed recently
        existing_analysis = ChatAnalysis.query.filter_by(
            content_hash=content_hash,
            user_id=user_id
        ).filter(
            ChatAnalysis.created_at > datetime.utcnow() - timedelta(hours=1)
        ).first()
        
        if existing_analysis:
            # Return existing analysis if recent
            log_audit_event(
                user_id=user_id,
                action='chat_analysis_retrieved',
                resource_type='chat',
                resource_id=str(existing_analysis.id),
                details={'content_hash': content_hash}
            )
            
            return jsonify({
                'message': 'Analysis retrieved from cache',
                'analysis': existing_analysis.to_dict()
            }), 200
        
        # Perform analysis
        analysis_result = analyze_chat_content_basic(chat_content)
        processing_time = time.time() - start_time
        
        # Store analysis
        chat_analysis = ChatAnalysis(
            user_id=user_id,
            chat_content=chat_content,
            analysis_result=json.dumps(analysis_result),
            sentiment_score=analysis_result.get('sentiment_score', 0.0),
            keywords=json.dumps(analysis_result.get('keywords', [])),
            entities=json.dumps(analysis_result.get('entities', [])),
            content_hash=content_hash,
            processing_time=processing_time
        )
        
        db.session.add(chat_analysis)
        db.session.commit()
        
        # Log analysis
        log_audit_event(
            user_id=user_id,
            action='chat_analyzed',
            resource_type='chat',
            resource_id=str(chat_analysis.id),
            details={
                'content_hash': content_hash,
                'sentiment': analysis_result.get('sentiment'),
                'urgency_level': analysis_result.get('urgency_level'),
                'contains_sensitive_info': analysis_result.get('contains_sensitive_info'),
                'processing_time': processing_time
            }
        )
        
        # Alert if sensitive information detected
        if analysis_result.get('contains_sensitive_info'):
            log_audit_event(
                user_id=user_id,
                action='sensitive_content_detected',
                resource_type='chat',
                resource_id=str(chat_analysis.id),
                details={'content_hash': content_hash}
            )
        
        return jsonify({
            'message': 'Chat analyzed successfully',
            'analysis': chat_analysis.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Analysis failed', 'details': str(e)}), 500


@analysis_bp.route('/forensics/<int:resource_id>', methods=['GET'])
@jwt_required()
def get_forensic_data(resource_id):
    """Get comprehensive forensic data for a resource"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.role not in ['admin', 'forensic_analyst']:
            return jsonify({'error': 'Insufficient permissions for forensic access'}), 403
        
        resource_type = request.args.get('type', 'document')
        
        if resource_type not in ['document', 'chat', 'user']:
            return jsonify({'error': 'Invalid resource type'}), 400
        
        # Get audit logs for the resource
        audit_logs = AuditLog.query.filter_by(
            resource_type=resource_type,
            resource_id=str(resource_id)
        ).order_by(AuditLog.timestamp.desc()).all()
        
        forensic_data = {
            'resource_id': resource_id,
            'resource_type': resource_type,
            'audit_trail': [log.to_dict() for log in audit_logs],
            'summary': {
                'total_events': len(audit_logs),
                'unique_users': len(set(log.user_id for log in audit_logs if log.user_id)),
                'unique_actions': len(set(log.action for log in audit_logs)),
                'date_range': {
                    'first_event': audit_logs[-1].timestamp.isoformat() if audit_logs else None,
                    'last_event': audit_logs[0].timestamp.isoformat() if audit_logs else None
                }
            }
        }
        
        # Add resource-specific data
        if resource_type == 'document':
            document = Document.query.get(resource_id)
            if document:
                forensic_data['resource_details'] = document.to_dict()
                
                # Verify current file integrity
                if os.path.exists(document.file_path):
                    with open(document.file_path, 'rb') as f:
                        current_hash = calculate_file_hash(f.read())
                    
                    forensic_data['integrity_status'] = {
                        'verified': current_hash == document.content_hash,
                        'original_hash': document.content_hash,
                        'current_hash': current_hash,
                        'last_verified': datetime.utcnow().isoformat()
                    }
        
        elif resource_type == 'chat':
            chat_analysis = ChatAnalysis.query.get(resource_id)
            if chat_analysis:
                forensic_data['resource_details'] = chat_analysis.to_dict()
        
        # Log forensic access
        log_audit_event(
            user_id=user_id,
            action='forensic_data_accessed',
            resource_type=resource_type,
            resource_id=str(resource_id),
            details={
                'accessed_by': user.username,
                'events_count': len(audit_logs)
            }
        )
        
        return jsonify({
            'message': 'Forensic data retrieved successfully',
            'forensic_data': forensic_data
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get forensic data', 'details': str(e)}), 500


@analysis_bp.route('/audit/logs', methods=['GET'])
@jwt_required()
def get_audit_logs():
    """Get audit logs with filtering and pagination"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.role not in ['admin', 'forensic_analyst']:
            return jsonify({'error': 'Insufficient permissions for audit access'}), 403
        
        # Pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 200)
        
        # Filter parameters
        action = request.args.get('action')
        resource_type = request.args.get('resource_type')
        target_user_id = request.args.get('user_id', type=int)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Build query
        query = AuditLog.query
        
        if action:
            query = query.filter(AuditLog.action.ilike(f'%{action}%'))
        
        if resource_type:
            query = query.filter_by(resource_type=resource_type)
        
        if target_user_id:
            query = query.filter_by(user_id=target_user_id)
        
        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date)
                query = query.filter(AuditLog.timestamp >= start_dt)
            except ValueError:
                return jsonify({'error': 'Invalid start_date format'}), 400
        
        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date)
                query = query.filter(AuditLog.timestamp <= end_dt)
            except ValueError:
                return jsonify({'error': 'Invalid end_date format'}), 400
        
        # Order by timestamp (newest first)
        query = query.order_by(AuditLog.timestamp.desc())
        
        # Paginate
        audit_logs = query.paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        # Log audit log access
        log_audit_event(
            user_id=user_id,
            action='audit_logs_accessed',
            resource_type='system',
            details={
                'accessed_by': user.username,
                'filters': {
                    'action': action,
                    'resource_type': resource_type,
                    'user_id': target_user_id,
                    'start_date': start_date,
                    'end_date': end_date
                },
                'results_count': len(audit_logs.items)
            }
        )
        
        return jsonify({
            'audit_logs': [log.to_dict() for log in audit_logs.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': audit_logs.total,
                'pages': audit_logs.pages,
                'has_next': audit_logs.has_next,
                'has_prev': audit_logs.has_prev
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get audit logs', 'details': str(e)}), 500


@analysis_bp.route('/chat/history', methods=['GET'])
@jwt_required()
def get_chat_history():
    """Get user's chat analysis history"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        
        # Get chat analyses for user
        chat_analyses = ChatAnalysis.query.filter_by(user_id=user_id).order_by(
            ChatAnalysis.created_at.desc()
        ).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return jsonify({
            'chat_history': [analysis.to_dict() for analysis in chat_analyses.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': chat_analyses.total,
                'pages': chat_analyses.pages,
                'has_next': chat_analyses.has_next,
                'has_prev': chat_analyses.has_prev
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get chat history', 'details': str(e)}), 500


@analysis_bp.route('/stats', methods=['GET'])
@jwt_required()
def get_analysis_stats():
    """Get analysis statistics for the user"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get time range
        days = request.args.get('days', 30, type=int)
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Document statistics
        total_documents = Document.query.filter_by(user_id=user_id).count()
        recent_documents = Document.query.filter_by(user_id=user_id).filter(
            Document.uploaded_at >= start_date
        ).count()
        
        # Chat analysis statistics
        total_chats = ChatAnalysis.query.filter_by(user_id=user_id).count()
        recent_chats = ChatAnalysis.query.filter_by(user_id=user_id).filter(
            ChatAnalysis.created_at >= start_date
        ).count()
        
        # Audit log statistics (if admin)
        audit_stats = {}
        if user.role in ['admin', 'forensic_analyst']:
            total_audit_logs = AuditLog.query.count()
            recent_audit_logs = AuditLog.query.filter(
                AuditLog.timestamp >= start_date
            ).count()
            audit_stats = {
                'total_audit_logs': total_audit_logs,
                'recent_audit_logs': recent_audit_logs
            }
        
        stats = {
            'user_stats': {
                'total_documents': total_documents,
                'recent_documents': recent_documents,
                'total_chats': total_chats,
                'recent_chats': recent_chats
            },
            'time_range': f'{days} days',
            **audit_stats
        }
        
        return jsonify({
            'message': 'Statistics retrieved successfully',
            'stats': stats
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get statistics', 'details': str(e)}), 500


@analysis_bp.route('/export', methods=['POST'])
@jwt_required()
@limiter.limit("3 per hour")
def export_analysis_data():
    """Export analysis data for court use"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.role not in ['admin', 'forensic_analyst']:
            return jsonify({'error': 'Insufficient permissions for data export'}), 403
        
        data = request.get_json() or {}
        export_type = data.get('export_type', 'full')  # full, documents, chats, audit
        
        export_data = {
            'export_metadata': {
                'generated_by': user.username,
                'generated_at': datetime.utcnow().isoformat(),
                'export_type': export_type,
                'system_version': '1.0.0'
            }
        }
        
        if export_type in ['full', 'documents']:
            documents = Document.query.filter_by(user_id=user_id).all()
            export_data['documents'] = [doc.to_dict() for doc in documents]
        
        if export_type in ['full', 'chats']:
            chats = ChatAnalysis.query.filter_by(user_id=user_id).all()
            export_data['chat_analyses'] = [chat.to_dict() for chat in chats]
        
        if export_type in ['full', 'audit']:
            audit_logs = AuditLog.query.filter_by(user_id=user_id).all()
            export_data['audit_logs'] = [log.to_dict() for log in audit_logs]
        
        # Log export
        log_audit_event(
            user_id=user_id,
            action='data_exported',
            resource_type='system',
            details={
                'export_type': export_type,
                'exported_by': user.username
            }
        )
        
        return jsonify({
            'message': 'Data exported successfully',
            'export_data': export_data
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Export failed', 'details': str(e)}), 500
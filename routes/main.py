from flask import Blueprint, render_template, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
from models import User, Document, ChatAnalysis, AuditLog
from app import db
import os

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')


@main_bp.route('/health')
def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        db.session.execute('SELECT 1')
        db_status = 'healthy'
    except Exception:
        db_status = 'unhealthy'
    
    return jsonify({
        'status': 'healthy',
        'database': db_status,
        'version': '1.0.0'
    }), 200


@main_bp.route('/api/dashboard')
@jwt_required()
def dashboard_data():
    """Get dashboard data for authenticated user"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get user statistics
        total_documents = Document.query.filter_by(user_id=user_id).count()
        processed_documents = Document.query.filter_by(user_id=user_id, is_processed=True).count()
        total_chats = ChatAnalysis.query.filter_by(user_id=user_id).count()
        
        # Get recent documents
        recent_documents = Document.query.filter_by(user_id=user_id).order_by(
            Document.uploaded_at.desc()
        ).limit(5).all()
        
        # Get recent chats
        recent_chats = ChatAnalysis.query.filter_by(user_id=user_id).order_by(
            ChatAnalysis.created_at.desc()
        ).limit(5).all()
        
        dashboard_data = {
            'user': user.to_dict(),
            'statistics': {
                'total_documents': total_documents,
                'processed_documents': processed_documents,
                'total_chats': total_chats,
                'processing_rate': (processed_documents / total_documents * 100) if total_documents > 0 else 0
            },
            'recent_documents': [doc.to_dict() for doc in recent_documents],
            'recent_chats': [chat.to_dict() for chat in recent_chats]
        }
        
        # Add admin statistics if user is admin
        if user.role in ['admin', 'forensic_analyst']:
            total_users = User.query.count()
            total_audit_logs = AuditLog.query.count()
            dashboard_data['admin_statistics'] = {
                'total_users': total_users,
                'total_audit_logs': total_audit_logs
            }
        
        return jsonify(dashboard_data), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get dashboard data', 'details': str(e)}), 500


@main_bp.route('/docs')
def api_documentation():
    """API documentation page"""
    return render_template('docs.html')


@main_bp.route('/upload')
def upload_page():
    """Document upload page"""
    return render_template('upload.html')


@main_bp.route('/documents')
def documents_page():
    """Documents management page"""
    return render_template('documents.html')


@main_bp.route('/analysis')
def analysis_page():
    """Analysis and chat page"""
    return render_template('analysis.html')


@main_bp.route('/admin')
def admin_page():
    """Admin panel page"""
    return render_template('admin.html')


@main_bp.errorhandler(404)
def not_found(error):
    """404 error handler"""
    return jsonify({'error': 'Resource not found'}), 404


@main_bp.errorhandler(500)
def internal_error(error):
    """500 error handler"""
    db.session.rollback()
    return jsonify({'error': 'Internal server error'}), 500


@main_bp.errorhandler(403)
def forbidden(error):
    """403 error handler"""
    return jsonify({'error': 'Access forbidden'}), 403


@main_bp.errorhandler(401)
def unauthorized(error):
    """401 error handler"""
    return jsonify({'error': 'Authentication required'}), 401
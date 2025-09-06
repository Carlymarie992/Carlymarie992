from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from datetime import datetime
from models import User, AuditLog
from app import db, limiter
from utils.helpers import log_audit_event, validate_password_strength
import ipaddress

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['POST'])
@limiter.limit("5 per minute")
def register():
    """User registration endpoint"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['username', 'email', 'password']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        username = data['username'].strip().lower()
        email = data['email'].strip().lower()
        password = data['password']
        
        # Validate password strength
        if not validate_password_strength(password):
            return jsonify({
                'error': 'Password must be at least 8 characters long and contain uppercase, lowercase, number, and special character'
            }), 400
        
        # Check if user already exists
        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'Username already exists'}), 409
        
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'Email already exists'}), 409
        
        # Create new user
        user = User(
            username=username,
            email=email,
            role=data.get('role', 'user')  # Default to user role
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        # Log registration
        log_audit_event(
            user_id=user.id,
            action='user_registered',
            resource_type='user',
            resource_id=str(user.id),
            details={'username': username, 'email': email}
        )
        
        return jsonify({
            'message': 'User registered successfully',
            'user': user.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Registration failed', 'details': str(e)}), 500


@auth_bp.route('/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    """User login endpoint"""
    try:
        data = request.get_json()
        
        # Validate required fields
        username = data.get('username', '').strip().lower()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        # Find user
        user = User.query.filter_by(username=username).first()
        
        if not user or not user.check_password(password):
            # Log failed login attempt
            log_audit_event(
                action='login_failed',
                resource_type='user',
                resource_id=username,
                details={'reason': 'invalid_credentials', 'username': username}
            )
            return jsonify({'error': 'Invalid credentials'}), 401
        
        if not user.is_active:
            # Log inactive user login attempt
            log_audit_event(
                user_id=user.id,
                action='login_failed',
                resource_type='user',
                resource_id=str(user.id),
                details={'reason': 'inactive_account', 'username': username}
            )
            return jsonify({'error': 'Account is inactive'}), 401
        
        # Update last login
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        # Create access token
        access_token = create_access_token(
            identity=user.id,
            additional_claims={
                'username': user.username,
                'role': user.role
            }
        )
        
        # Log successful login
        log_audit_event(
            user_id=user.id,
            action='login_successful',
            resource_type='user',
            resource_id=str(user.id),
            details={'username': username}
        )
        
        return jsonify({
            'access_token': access_token,
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Login failed', 'details': str(e)}), 500


@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """User logout endpoint"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if user:
            # Log logout
            log_audit_event(
                user_id=user.id,
                action='logout',
                resource_type='user',
                resource_id=str(user.id),
                details={'username': user.username}
            )
        
        # Note: JWT tokens are stateless, so we can't invalidate them server-side
        # In production, you might want to implement a token blacklist
        
        return jsonify({'message': 'Logged out successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': 'Logout failed', 'details': str(e)}), 500


@auth_bp.route('/profile', methods=['GET'])
@jwt_required()
def get_profile():
    """Get current user profile"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({'user': user.to_dict()}), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get profile', 'details': str(e)}), 500


@auth_bp.route('/change-password', methods=['POST'])
@jwt_required()
@limiter.limit("3 per minute")
def change_password():
    """Change user password"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        
        if not current_password or not new_password:
            return jsonify({'error': 'Current and new passwords are required'}), 400
        
        # Verify current password
        if not user.check_password(current_password):
            # Log failed password change
            log_audit_event(
                user_id=user.id,
                action='password_change_failed',
                resource_type='user',
                resource_id=str(user.id),
                details={'reason': 'invalid_current_password'}
            )
            return jsonify({'error': 'Invalid current password'}), 401
        
        # Validate new password strength
        if not validate_password_strength(new_password):
            return jsonify({
                'error': 'New password must be at least 8 characters long and contain uppercase, lowercase, number, and special character'
            }), 400
        
        # Update password
        user.set_password(new_password)
        db.session.commit()
        
        # Log successful password change
        log_audit_event(
            user_id=user.id,
            action='password_changed',
            resource_type='user',
            resource_id=str(user.id),
            details={'username': user.username}
        )
        
        return jsonify({'message': 'Password changed successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Password change failed', 'details': str(e)}), 500
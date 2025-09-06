from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import os
import json
import time
from datetime import datetime, timedelta
import re
from models import Document, DocumentSummary, DocumentRedaction, DocumentTimeline, User
from app import db, limiter
from utils.helpers import log_audit_event, redact_text, extract_keywords, create_chain_of_custody_record

processing_bp = Blueprint('processing', __name__)


def extract_text_from_file(file_path, file_type):
    """Extract text content from various file types"""
    try:
        if file_type == 'document':
            if file_path.lower().endswith('.pdf'):
                return extract_pdf_text(file_path)
            elif file_path.lower().endswith(('.doc', '.docx')):
                return extract_docx_text(file_path)
            elif file_path.lower().endswith('.txt'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
        return None
    except Exception as e:
        raise Exception(f"Text extraction failed: {str(e)}")


def extract_pdf_text(file_path):
    """Extract text from PDF files"""
    try:
        import PyPDF2
        text = ""
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        return text
    except ImportError:
        raise Exception("PyPDF2 not installed - PDF processing unavailable")
    except Exception as e:
        raise Exception(f"PDF extraction failed: {str(e)}")


def extract_docx_text(file_path):
    """Extract text from DOCX files"""
    try:
        from docx import Document as DocxDocument
        doc = DocxDocument(file_path)
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text
    except ImportError:
        raise Exception("python-docx not installed - DOCX processing unavailable")
    except Exception as e:
        raise Exception(f"DOCX extraction failed: {str(e)}")


def generate_summary_basic(text, summary_type='brief'):
    """
    Basic text summarization (placeholder for AI integration)
    In production, this would integrate with OpenAI, Azure Cognitive Services, etc.
    """
    if not text or len(text.strip()) < 100:
        return "Document too short for meaningful summary."
    
    # Basic extractive summarization
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    
    if summary_type == 'brief':
        # Return first few sentences
        summary_length = min(3, len(sentences))
        return '. '.join(sentences[:summary_length]) + '.'
    elif summary_type == 'detailed':
        # Return more sentences with key points
        summary_length = min(10, len(sentences))
        return '. '.join(sentences[:summary_length]) + '.'
    elif summary_type == 'key_points':
        # Extract potential key points (sentences with certain keywords)
        key_terms = ['important', 'significant', 'concluded', 'determined', 'found', 'evidence', 'result']
        key_sentences = []
        for sentence in sentences:
            if any(term in sentence.lower() for term in key_terms):
                key_sentences.append(sentence)
        
        if key_sentences:
            return '. '.join(key_sentences[:5]) + '.'
        else:
            return '. '.join(sentences[:3]) + '.'
    
    return "Summary generation failed."


def extract_timeline_events_basic(text):
    """
    Basic timeline extraction (placeholder for AI integration)
    """
    events = []
    
    # Look for date patterns
    date_patterns = [
        r'\b(\d{1,2}/\d{1,2}/\d{4})\b',  # MM/DD/YYYY
        r'\b(\d{1,2}-\d{1,2}-\d{4})\b',  # MM-DD-YYYY
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b',
        r'\b(\d{4}-\d{2}-\d{2})\b'  # YYYY-MM-DD
    ]
    
    sentences = re.split(r'[.!?]+', text)
    
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 20:
            continue
            
        for pattern in date_patterns:
            matches = re.finditer(pattern, sentence, re.IGNORECASE)
            for match in matches:
                date_str = match.group()
                try:
                    # Try to parse the date
                    if '/' in date_str:
                        event_date = datetime.strptime(date_str, '%m/%d/%Y')
                    elif '-' in date_str and len(date_str) == 10:
                        event_date = datetime.strptime(date_str, '%Y-%m-%d')
                    else:
                        # For named months, use a simple approach
                        continue
                    
                    events.append({
                        'date': event_date,
                        'description': sentence,
                        'confidence': 0.7  # Basic confidence score
                    })
                    break
                except ValueError:
                    continue
    
    # Sort events by date
    events.sort(key=lambda x: x['date'])
    
    return events


@processing_bp.route('/documents/<int:document_id>/summarize', methods=['POST'])
@jwt_required()
@limiter.limit("5 per minute")
def summarize_document(document_id):
    """Generate document summary"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get document
        document = Document.query.filter_by(id=document_id, user_id=user_id).first()
        
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        data = request.get_json() or {}
        summary_type = data.get('summary_type', 'brief')  # brief, detailed, key_points
        
        if summary_type not in ['brief', 'detailed', 'key_points']:
            return jsonify({'error': 'Invalid summary type'}), 400
        
        start_time = time.time()
        
        # Extract text from document
        if not os.path.exists(document.file_path):
            return jsonify({'error': 'Document file not found'}), 404
        
        text_content = extract_text_from_file(document.file_path, document.file_type)
        
        if not text_content:
            return jsonify({'error': 'Could not extract text from document'}), 400
        
        # Generate summary
        summary_content = generate_summary_basic(text_content, summary_type)
        processing_time = time.time() - start_time
        
        # Check if summary already exists
        existing_summary = DocumentSummary.query.filter_by(
            document_id=document_id,
            summary_type=summary_type
        ).first()
        
        if existing_summary:
            # Update existing summary
            existing_summary.content = summary_content
            existing_summary.created_at = datetime.utcnow()
            existing_summary.processing_time = processing_time
            db.session.commit()
            summary = existing_summary
        else:
            # Create new summary
            summary = DocumentSummary(
                document_id=document_id,
                summary_type=summary_type,
                content=summary_content,
                confidence_score=0.8,  # Basic confidence
                processing_time=processing_time
            )
            db.session.add(summary)
            db.session.commit()
        
        # Update document processing status
        document.processing_status = 'completed'
        document.is_processed = True
        db.session.commit()
        
        # Create chain of custody record
        create_chain_of_custody_record(
            document_id=document.id,
            action='summarized',
            user_id=user_id,
            details={
                'summary_type': summary_type,
                'processing_time': processing_time
            }
        )
        
        # Log processing
        log_audit_event(
            user_id=user_id,
            action='document_summarized',
            resource_type='document',
            resource_id=str(document_id),
            details={
                'filename': document.original_filename,
                'summary_type': summary_type,
                'processing_time': processing_time
            }
        )
        
        return jsonify({
            'message': 'Document summarized successfully',
            'summary': summary.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Summarization failed', 'details': str(e)}), 500


@processing_bp.route('/documents/<int:document_id>/redact', methods=['POST'])
@jwt_required()
@limiter.limit("10 per minute")
def redact_document(document_id):
    """Apply redactions to document text"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get document
        document = Document.query.filter_by(id=document_id, user_id=user_id).first()
        
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        data = request.get_json() or {}
        redaction_type = data.get('redaction_type', 'pii')  # pii, sensitive, custom
        custom_patterns = data.get('custom_patterns', [])
        redaction_text = data.get('redaction_text', '***REDACTED***')
        
        # Extract text from document
        if not os.path.exists(document.file_path):
            return jsonify({'error': 'Document file not found'}), 404
        
        text_content = extract_text_from_file(document.file_path, document.file_type)
        
        if not text_content:
            return jsonify({'error': 'Could not extract text from document'}), 400
        
        # Apply redactions
        if redaction_type == 'custom' and custom_patterns:
            redacted_text = text_content
            redactions_made = []
            
            for pattern in custom_patterns:
                matches = list(re.finditer(pattern, redacted_text, re.IGNORECASE))
                for match in matches:
                    redactions_made.append({
                        'type': 'custom',
                        'pattern': pattern,
                        'original': match.group(),
                        'start': match.start(),
                        'end': match.end()
                    })
                redacted_text = re.sub(pattern, redaction_text, redacted_text, flags=re.IGNORECASE)
        else:
            # Use built-in redaction patterns
            redacted_text, redactions_made = redact_text(text_content, redaction_text)
        
        # Store redaction records
        for redaction_info in redactions_made:
            redaction_record = DocumentRedaction(
                document_id=document_id,
                redaction_type=redaction_type,
                start_position=redaction_info.get('start', 0),
                end_position=redaction_info.get('end', 0),
                original_text=redaction_info.get('original', ''),
                redacted_text=redaction_text,
                reason=f"Automatic {redaction_type} redaction",
                applied_by=user_id
            )
            db.session.add(redaction_record)
        
        db.session.commit()
        
        # Create chain of custody record
        create_chain_of_custody_record(
            document_id=document.id,
            action='redacted',
            user_id=user_id,
            details={
                'redaction_type': redaction_type,
                'redactions_count': len(redactions_made)
            }
        )
        
        # Log redaction
        log_audit_event(
            user_id=user_id,
            action='document_redacted',
            resource_type='document',
            resource_id=str(document_id),
            details={
                'filename': document.original_filename,
                'redaction_type': redaction_type,
                'redactions_count': len(redactions_made)
            }
        )
        
        return jsonify({
            'message': 'Document redacted successfully',
            'redactions_count': len(redactions_made),
            'redacted_text': redacted_text[:1000] + '...' if len(redacted_text) > 1000 else redacted_text
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Redaction failed', 'details': str(e)}), 500


@processing_bp.route('/documents/<int:document_id>/timeline', methods=['POST'])
@jwt_required()
@limiter.limit("5 per minute")
def generate_timeline(document_id):
    """Generate timeline from document content"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get document
        document = Document.query.filter_by(id=document_id, user_id=user_id).first()
        
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        start_time = time.time()
        
        # Extract text from document
        if not os.path.exists(document.file_path):
            return jsonify({'error': 'Document file not found'}), 404
        
        text_content = extract_text_from_file(document.file_path, document.file_type)
        
        if not text_content:
            return jsonify({'error': 'Could not extract text from document'}), 400
        
        # Extract timeline events
        timeline_events = extract_timeline_events_basic(text_content)
        processing_time = time.time() - start_time
        
        # Clear existing timeline events for this document
        DocumentTimeline.query.filter_by(document_id=document_id).delete()
        
        # Store timeline events
        timeline_records = []
        for event in timeline_events:
            timeline_record = DocumentTimeline(
                document_id=document_id,
                event_date=event['date'],
                event_type='extracted',
                event_description=event['description'],
                confidence_score=event['confidence']
            )
            db.session.add(timeline_record)
            timeline_records.append(timeline_record)
        
        db.session.commit()
        
        # Create chain of custody record
        create_chain_of_custody_record(
            document_id=document.id,
            action='timeline_generated',
            user_id=user_id,
            details={
                'events_extracted': len(timeline_events),
                'processing_time': processing_time
            }
        )
        
        # Log timeline generation
        log_audit_event(
            user_id=user_id,
            action='document_timeline_generated',
            resource_type='document',
            resource_id=str(document_id),
            details={
                'filename': document.original_filename,
                'events_extracted': len(timeline_events),
                'processing_time': processing_time
            }
        )
        
        return jsonify({
            'message': 'Timeline generated successfully',
            'events_count': len(timeline_events),
            'timeline': [record.to_dict() for record in timeline_records],
            'processing_time': processing_time
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Timeline generation failed', 'details': str(e)}), 500


@processing_bp.route('/documents/<int:document_id>/transcribe', methods=['POST'])
@jwt_required()
@limiter.limit("3 per minute")  # Lower limit for intensive operations
def transcribe_document(document_id):
    """Transcribe audio/video documents (placeholder implementation)"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get document
        document = Document.query.filter_by(id=document_id, user_id=user_id).first()
        
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        if document.file_type not in ['audio', 'video']:
            return jsonify({'error': 'Document is not audio or video'}), 400
        
        # This is a placeholder - in production, integrate with:
        # - Azure Speech Services
        # - Google Cloud Speech-to-Text
        # - AWS Transcribe
        # - OpenAI Whisper
        
        start_time = time.time()
        
        # Placeholder transcription
        transcription = f"[PLACEHOLDER TRANSCRIPTION] This is a placeholder transcription for {document.original_filename}. " \
                      f"In production, this would contain the actual transcribed audio/video content using AI services."
        
        processing_time = time.time() - start_time
        
        # Store as summary with type 'transcription'
        existing_transcription = DocumentSummary.query.filter_by(
            document_id=document_id,
            summary_type='transcription'
        ).first()
        
        if existing_transcription:
            existing_transcription.content = transcription
            existing_transcription.created_at = datetime.utcnow()
            existing_transcription.processing_time = processing_time
            db.session.commit()
            summary = existing_transcription
        else:
            summary = DocumentSummary(
                document_id=document_id,
                summary_type='transcription',
                content=transcription,
                confidence_score=0.9,  # High confidence for placeholder
                processing_time=processing_time
            )
            db.session.add(summary)
            db.session.commit()
        
        # Create chain of custody record
        create_chain_of_custody_record(
            document_id=document.id,
            action='transcribed',
            user_id=user_id,
            details={'processing_time': processing_time}
        )
        
        # Log transcription
        log_audit_event(
            user_id=user_id,
            action='document_transcribed',
            resource_type='document',
            resource_id=str(document_id),
            details={
                'filename': document.original_filename,
                'processing_time': processing_time
            }
        )
        
        return jsonify({
            'message': 'Document transcribed successfully',
            'transcription': summary.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Transcription failed', 'details': str(e)}), 500


@processing_bp.route('/documents/<int:document_id>/summaries', methods=['GET'])
@jwt_required()
def get_document_summaries(document_id):
    """Get all summaries for a document"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Verify document ownership
        document = Document.query.filter_by(id=document_id, user_id=user_id).first()
        
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        # Get summaries
        summaries = DocumentSummary.query.filter_by(document_id=document_id).all()
        
        return jsonify({
            'summaries': [summary.to_dict() for summary in summaries]
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get summaries', 'details': str(e)}), 500


@processing_bp.route('/documents/<int:document_id>/redactions', methods=['GET'])
@jwt_required()
def get_document_redactions(document_id):
    """Get all redactions for a document"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Verify document ownership
        document = Document.query.filter_by(id=document_id, user_id=user_id).first()
        
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        # Get redactions
        redactions = DocumentRedaction.query.filter_by(document_id=document_id).all()
        
        return jsonify({
            'redactions': [redaction.to_dict() for redaction in redactions]
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get redactions', 'details': str(e)}), 500


@processing_bp.route('/documents/<int:document_id>/timeline', methods=['GET'])
@jwt_required()
def get_document_timeline(document_id):
    """Get timeline for a document"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Verify document ownership
        document = Document.query.filter_by(id=document_id, user_id=user_id).first()
        
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        # Get timeline events
        timeline_events = DocumentTimeline.query.filter_by(document_id=document_id).order_by(DocumentTimeline.event_date).all()
        
        return jsonify({
            'timeline': [event.to_dict() for event in timeline_events]
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get timeline', 'details': str(e)}), 500
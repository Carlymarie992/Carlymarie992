# Secure Document Processing System

A comprehensive system for secure document processing, analysis, and organization for court trial use.

## Features

- **Secure Document Upload**: Large document upload with validation and encryption
- **Document Processing**: AI-powered summarization, transcription, and analysis
- **Redaction Tools**: Secure text and data redaction capabilities
- **Timeline Creation**: Automated chronological organization of events
- **Court Trial Organization**: Specialized tools for legal document management
- **Forensic Logging**: Comprehensive audit trails and evidence integrity
- **Secure API**: Protected endpoints with authentication and rate limiting

## Security Features

- JWT-based authentication
- Encrypted file storage
- Comprehensive audit logging
- Rate limiting and CORS protection
- Secure hash verification for evidence integrity
- Access control and user management

## Quick Start

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Initialize the database:
```bash
python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all()"
```

4. Run the application:
```bash
python app.py
```

## API Documentation

### Authentication
- `POST /api/auth/login` - User login
- `POST /api/auth/register` - User registration
- `POST /api/auth/logout` - User logout

### Document Management
- `POST /api/documents/upload` - Upload documents
- `GET /api/documents` - List documents
- `GET /api/documents/<id>` - Get document details
- `DELETE /api/documents/<id>` - Delete document

### Document Processing
- `POST /api/documents/<id>/summarize` - Generate summary
- `POST /api/documents/<id>/transcribe` - Transcribe audio/video
- `POST /api/documents/<id>/redact` - Apply redactions
- `POST /api/documents/<id>/timeline` - Generate timeline

### Analysis & Forensics
- `GET /api/audit/logs` - Access audit logs
- `POST /api/analysis/chat` - Submit chat for analysis
- `GET /api/analysis/forensics/<id>` - Get forensic data

## Configuration

See `.env.example` for all available configuration options.

## Author

Carly Marie - [GitHub Profile](https://github.com/Carlymarie992)

## License

This project is for professional legal use. See LICENSE file for details.
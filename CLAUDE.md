# Waddle Web Development Guide

## Project Overview

Waddle Web is a podcast editing web application that integrates with the Waddle preprocessing library. It provides a complete pipeline for podcast creation including audio file processing, transcription, editing, and final export functionality with automated metadata and chapter generation.

## Architecture

This is a full-stack web application with a monorepo structure:

### Backend (`waddle-api/`)
- **Framework**: FastAPI (Python 3.13+)
- **Database**: SQLite with SQLModel ORM
- **Dependencies**: Managed by `uv` package manager
- **Key Features**: Audio processing, transcription, async job processing
- **Integration**: Uses `waddle-ai` library for audio processing

### Frontend (`waddle-ui/`)
- **Framework**: React 19 with TypeScript
- **Router**: TanStack Router with file-based routing
- **UI Library**: Chakra UI v3
- **Styling**: CSS with Emotion
- **Build Tool**: Vite
- **Package Manager**: pnpm
- **Testing**: Cypress for E2E tests

## Development Setup

### Quick Start
```bash
# Backend setup
cd waddle-api
uv pip install -e ".[dev]"
uv run fastapi dev # Runs on http://127.0.0.1:8000

# Frontend setup (in separate terminal)
cd waddle-ui
pnpm install
pnpm dev  # Runs on http://localhost:5173
```

### Environment Requirements
- **Python**: 3.13+
- **Node.js**: Latest LTS
- **Package Managers**: uv (Python), pnpm (Node.js)

## Key Commands

### Backend (`waddle-api/`)
- **Dev server**: `uvicorn app.main:app --reload`
- **Tests**: `pytest` / `pytest --cov=app`
- **Linting**: `ruff check .` / `ruff format .`
- **Type check**: `pyright`
- **Database migrations**: `alembic revision --autogenerate -m "message"` / `alembic upgrade head`

### Frontend (`waddle-ui/`)
- **Dev server**: `pnpm dev`
- **Build**: `pnpm build`
- **Linting/Formatting**: `pnpm lint` / `pnpm format` (uses Biome)
- **API client generation**: `pnpm generate-client` (generates from OpenAPI spec)
- **E2E tests**: `pnpm cy` / `pnpm cy:open`

## Code Style & Standards

### General Principles
- **Write simple, readable code**: Prefer clarity over cleverness
- **Avoid over-engineering**: Use straightforward solutions unless complexity is justified
- **Minimize abstractions**: Don't create unnecessary layers or indirection
- **Use existing patterns**: Follow established patterns in the codebase
- **Keep functions small**: Single responsibility, easy to understand and test

### Backend (Python)
- **Line length**: 160 characters (configured in pyproject.toml)
- **Formatter**: Ruff with double quotes, 4-space indentation
- **Type checking**: Strict mode with Pyright
- **Import organization**: Standard library → Third-party → Local
- **Async patterns**: FastAPI with background tasks for long-running operations
- **Keep it simple**: Prefer direct implementations over complex abstractions

### Frontend (TypeScript/React)
- **Formatter**: Biome with tab indentation, double quotes
- **Component patterns**: Functional components with hooks
- **State management**: React hooks (useState, useEffect, etc.)
- **File organization**: File-based routing with TanStack Router
- **API integration**: Generated client from OpenAPI spec
- **Keep it simple**: Avoid unnecessary custom hooks or complex state patterns

## Application Features & Workflow

### Episode Processing Pipeline
1. **Upload**: Users upload audio files (reference + speaker-specific tracks)
2. **Preprocess**: Audio alignment and normalization using Waddle library
3. **Postprocess**: Transcription generation and editing
4. **Metadata**: Automated chapter and show notes generation
5. **Export**: Final MP3 with embedded metadata

### Current Implementation Status
- ✅ Episode creation and deletion
- ✅ File upload handling
- ✅ Processing status tracking with visual indicators
- ✅ Real-time status polling
- ✅ E2E test coverage
- 🔄 Episode editing interface (placeholder)
- 🔄 Transcription editing
- 🔄 Metadata generation interface

## API Integration

### Client Generation
The frontend uses automatically generated API clients:
```bash
cd waddle-ui
pnpm generate-client  # Generates from http://127.0.0.1:8000/openapi.json
```

### Key API Endpoints
- `POST /v1/episodes` - Create episode with file upload
- `GET /v1/episodes` - List episodes with status
- `DELETE /v1/episodes/{uuid}` - Delete episode
- Background processing endpoints for audio processing

## Database Schema

### Core Models
- **Episode**: Main entity with processing status flags
- **SourceFile**: Original uploaded audio files
- **ProcessedFile**: Generated audio files at various stages
- **Transcription**: SRT files (generated and annotated)
- **ProcessingJob**: Async job tracking

## Testing

### E2E Testing (Cypress)
- Located in `waddle-ui/cypress/e2e/`
- Tests full episode creation → processing → deletion workflow
- Uses real audio files from `waddle-api/tests/ep0/`
- Configured for localhost API at 127.0.0.1:8000

### Running Tests
```bash
cd waddle-ui
pnpm cy:open  # Interactive mode
pnpm cy       # Headless mode
```

## File Structure

```
waddle-web/
├── waddle-api/              # FastAPI backend
│   ├── app/
│   │   ├── main.py         # FastAPI app setup
│   │   ├── db.py           # Database configuration
│   │   ├── models.py       # SQLModel definitions
│   │   └── v1/router.py    # API routes
│   ├── tests/              # Test files and fixtures
│   └── pyproject.toml      # Python dependencies
├── waddle-ui/              # React frontend
│   ├── src/
│   │   ├── routes/         # File-based routing
│   │   ├── components/     # Reusable UI components
│   │   ├── client/         # Generated API client
│   │   └── App.tsx         # Main app component
│   ├── cypress/            # E2E tests
│   └── package.json        # Node dependencies
├── docs/api/               # API documentation
└── waddle-web.code-workspace # VS Code workspace
```

## Development Tips

### Working with Audio Files
- Audio files for testing are in `waddle-api/tests/ep0/`
- The app handles both reference files (GMT prefix) and speaker-specific files
- Processing can take several minutes for large files

### Database Development
- SQLite database is created automatically on first run
- Located at `waddle-api/database.db`
- Use Alembic for schema migrations

### API Development
- OpenAPI spec auto-generated at `/openapi.json`
- CORS enabled for frontend development
- Background tasks used for long-running audio processing

### Frontend Development
- Hot reload enabled with Vite
- TanStack Router generates route tree automatically
- Chakra UI provides comprehensive component library
- Real-time status updates via polling (5-second intervals)

## Troubleshooting

### Common Issues
1. **Port conflicts**: API runs on 8000, UI on 5173
2. **API client out of sync**: Run `pnpm generate-client` after API changes
3. **Processing timeouts**: Large audio files may take 5+ minutes to process
4. **File upload limits**: Check FastAPI file size limits for large audio files

### Development Workflow
1. Start backend first (`uvicorn app.main:app --reload`)
2. Generate API client if schema changed
3. Start frontend (`pnpm dev`)
4. Use browser dev tools + FastAPI docs for debugging

## Production Considerations

### Deployment
- Backend: Container-ready with Dockerfile
- Frontend: Static build with `pnpm build`
- Database: Consider PostgreSQL for production
- File storage: Consider cloud storage for audio files

### Monitoring
- FastAPI provides automatic OpenAPI documentation
- Background job status tracking implemented
- Error handling with user-friendly messages

## Code Quality Rules

### CRITICAL: Pre-commit Requirements
When working on code, you MUST run these commands before finishing:

**For waddle-api/ changes:**
```bash
cd waddle-api
uv run format
uv run lint
```
Fix any issues that arise before considering the work complete.

**For waddle-ui/ changes:**
```bash
cd waddle-ui
pnpm format
pnpm lint
```
Fix any issues that arise before considering the work complete.

## Contributing

### Before Making Changes
1. Run tests: `pytest` (backend) and `pnpm cy` (frontend)
2. Check linting: `ruff check .` and `pnpm lint`
3. Update API client if backend changes: `pnpm generate-client`
4. Test E2E workflow with real audio files

### Code Review Checklist
- [ ] Tests pass
- [ ] Code follows style guidelines
- [ ] API changes documented
- [ ] Breaking changes noted
- [ ] Performance impact considered for audio processing
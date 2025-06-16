# Waddle API Development Guide

## Development Commands
- **Run the app**: `uvicorn app.main:app --reload`
- **Run in Docker**: `docker-compose up`
- **Install dependencies**: `uv pip install -e .`
- **Install dev dependencies**: `uv pip install -e ".[dev]"`
- **Run tests**: `pytest`
- **Run single test**: `pytest tests/path/to/test.py::test_function`
- **Run with coverage**: `pytest --cov=app`
- **Lint code**: `ruff check .`
- **Format code**: `ruff format .`
- **Type check**: `pyright`
- **Create migration**: `alembic revision --autogenerate -m "message"`
- **Run migrations**: `alembic upgrade head`

## Code Style Guidelines
- **Python version**: 3.12
- **Line length**: 79 characters
- **Quotes**: Double quotes
- **Indentation**: Spaces (4)
- **Imports**: Group standard library, third-party, and local imports
- **Type annotations**: Required for all function parameters and return values
- **Naming**: snake_case for variables/functions, PascalCase for classes
- **Error handling**: Use explicit try/except blocks with specific exceptions
- **Documentation**: Docstrings for modules, classes, and functions
- **Linting rules**: Ruff with E (errors) and F (code style) rule sets
- **Database**: SQLModel with SQLite (for development)

The FastAPI app is structured in the `app/` directory with dependency management via `uv`.
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CTFd is a Capture The Flag (CTF) competition framework built with Flask (Python) and Vue 3. It provides a complete platform for running CTF competitions with features like dynamic scoring, team management, and a plugin system.

## Common Commands

### Development Server
```bash
python serve.py              # Start dev server (default port 4000)
python serve.py --port 8000  # Custom port
flask run                    # Alternative using Flask CLI
```

### Testing
```bash
make test                    # Run full test suite with coverage + security checks
pytest tests/test_file.py   # Run specific test file
pytest tests/test_file.py::test_function -v  # Run single test
pytest -x                    # Stop on first failure
```

Tests use SQLite by default. Set `TESTING_DATABASE_URL` env var for other databases.

### Linting and Formatting
```bash
make lint                    # Check all linting (Python + JS + Markdown)
make format                  # Auto-format code
```

Python uses Black + isort + ruff. JavaScript uses ESLint + Prettier.

### Database
```bash
python manage.py db upgrade  # Run migrations
python manage.py db migrate  # Create new migration
python manage.py shell       # Interactive shell with app context
```

### Admin Theme (Vue 3)
```bash
cd CTFd/themes/admin
yarn install                 # Install dependencies
yarn build                   # Production build
yarn dev                     # Dev server with HMR
```

## Architecture

### Entry Points
- `serve.py` - Development server with gevent monkey patching
- `wsgi.py` - Production WSGI entry point
- `manage.py` - Flask CLI (migrations, shell)

### Core Application (`CTFd/`)
- `__init__.py` - Flask app factory (`create_app()`), initializes all components
- `config.py` - Configuration classes (uses `config.ini` with env interpolation)
- `auth.py` - Authentication routes and session handling
- `views.py` - Public-facing routes

### Data Layer
- `models/__init__.py` - All SQLAlchemy models in single file (Users, Teams, Challenges, Solves, etc.)
- `schemas/` - Marshmallow schemas for API serialization
- `migrations/` - Alembic database migrations

### API (`api/v1/`)
REST API using Flask-RESTX. Key endpoints:
- `challenges.py` - Challenge CRUD and solving
- `users.py`, `teams.py` - User/team management
- `submissions.py` - Flag submission handling
- `scoreboard.py` - Leaderboard data

### Plugin System (`plugins/`)
Plugins can add challenge types, flag validators, routes, and templates:
- `challenges/` - Standard challenge type
- `dynamic_challenges/` - Dynamic scoring
- `flags/` - Static and regex flag validators

Load custom plugins by placing them in `CTFd/plugins/`. Plugins are initialized via `init_plugins()` in app startup.

### Theme System (`themes/`)
- `admin/` - Vue 3 + Vite admin dashboard
- `core/` - Default public theme (Jinja2 templates)

Themes use a custom `ThemeLoader` allowing dynamic theme switching and template overrides.

## Testing Patterns

Tests use helpers from `tests/helpers.py`:

```python
from tests.helpers import create_ctfd, destroy_ctfd, login_as_user, gen_challenge, gen_flag, gen_user

def test_example():
    app = create_ctfd()  # Creates test app with fresh DB
    try:
        with app.app_context():
            # gen_* functions create test data
            user = gen_user(db, name="testuser")
            challenge = gen_challenge(db)
            flag = gen_flag(db, challenge_id=challenge.id, content="flag{test}")

            # login_as_user returns authenticated test client
            client = login_as_user(app, name="testuser")
            response = client.get("/api/v1/challenges")
    finally:
        destroy_ctfd(app)  # Cleanup database
```

Time-sensitive tests use `ctftime` context managers:
```python
with ctftime.started():
    # Test runs during competition
```

## Key Patterns

### Configuration
Config values are stored in the database `Configs` table and cached. Access via:
```python
from CTFd.utils import get_config, set_config
value = get_config("key")
set_config("key", "value")
```

### Cache Invalidation
Clear caches after modifying related data:
```python
from CTFd.cache import clear_challenges, clear_standings
clear_standings()  # After score changes
clear_challenges()  # After challenge modifications
```

### Authentication Decorators
```python
from CTFd.utils.decorators import authed_only, admins_only, require_team
```

## Database Support

Supports SQLite (dev/testing), MySQL/MariaDB, and PostgreSQL. Configure via `SQLALCHEMY_DATABASE_URI` in config.ini or environment.

# ExpenSOS

ExpenSOS is a self‑hosted personal finance tracker built with Flask, PostgreSQL, and a lean front-end that blends Tailwind-inspired tokens with custom CSS/JS. The project supports authenticated users, expense/budget management, recurring transactions, reminders, receipt uploads, basic insights, and a Chart.js dashboard.

## Getting started
1. Create and activate a Python virtual environment (the repo already includes `venv/` for reference, so you can reuse it or recreate one with `python -m venv venv`).
2. Start PostgreSQL and set `DATABASE_URL` to point at it.
3. Install the server dependencies with `pip install -r backend/requirements.txt`.
4. Run `python backend/app.py`. The app binds to `http://0.0.0.0:6969` in debug mode.
5. Visit `http://localhost:6969/login`, or register a new account. The seeded admin account is `admin@example.com` / `admin123`.
6. Custom assets (Tailwind CLI, translations, templates) live under `frontend/`; they are served by the Flask backend configured in `backend/app.py`.

## Directory layout
- `backend/`: all Python code that powers the server, including `app.py`, helpers, migration scripts, and dependency manifest.
  - `uploads/`: receipt images uploaded through the `/add` and `/upload-receipt` flows.
  - `migrate_sqlite_to_postgres.py`: one-time importer for moving legacy SQLite data into PostgreSQL.
  - `patch_templates.py`, `add_svg_sizes.py`, `fix_nav.py`, `fix_svgs.py`: CLI utilities that operate on the `frontend/templates`.
- `frontend/`: Jinja2 templates and static assets.
  - `templates/`: page shells (`base.html`, `auth_base.html`) and views for dashboard, expenses, budgets, recurring schedules, reminders, settings, etc.
  - `static/`: the small helper JS and placeholder CSS files that keep chart interactions and keyboard shortcuts working.
  - `input.css` + `tailwind.config.js` + `tailwindcss.exe`: optional Tailwind tooling; the current UI relies on the hand-crafted CSS embedded in `base.html`, but the input file can be compiled if you ever decide to extract the tokens into a bundled stylesheet.

## Key tools & Stack
- **Backend**: Flask handles routing, sessions, flash messaging, JSON APIs, and file uploads. Werkzeug is used for password hashing and secure filenames.
- **Database**: PostgreSQL stores users, settings, expenses, budgets, recurring items, and reminders. Schema setup and the legacy SQLite migration helper live in `backend/database.py`.
- **Frontend**: Jinja2 templates plug into Chart.js for the category dashboard, and Google Fonts + inline CSS tokens deliver the design system.
- **Tailwind tooling**: `frontend/input.css` defines the Tailwind imports, and `frontend/tailwindconfig.js` configures colors/animations. Use the bundled `frontend/tailwindcss.exe` (or your own Tailwind CLI) to compile if you need a dedicated CSS output.
- **Translations**: `backend/translations.py` keeps English and Hindi copy centralized for reuse across templates.

## Maintenance & utilities
- `backend/patch_templates.py`: cleans up inline Tailwind CDN snippets and patches auth styles inside the frontend templates/input CSS.
- `backend/add_svg_sizes.py`: ensures SVG icons have explicit `width`/`height` attributes so browsers can size them consistently.
- `backend/fix_nav.py` and `backend/fix_svgs.py`: helper scripts to normalize navigation classes and SVG sizing across templates.
- `backend/migrate_sqlite_to_postgres.py`: imports the legacy SQLite data file into PostgreSQL.

## Running & deployment notes
- The Flask app uses `backend/app.py` as the entry point and explicitly sets `template_folder`/`static_folder` to `frontend/` so the reorganized tree works without additional configuration.
- Uploaded files live under `backend/uploads`; confirm that folder is writable by the process running the server to avoid HTTP 500s when saving receipts.
- PostgreSQL connection settings are read from `DATABASE_URL`. The default Docker Compose value is `postgresql://expensos:expensos@db:5432/expensos`.
- Chart.js is loaded from `https://cdn.jsdelivr.net/npm/chart.js` directly inside `frontend/templates/base.html`.

## Production deployment
This project is best deployed as a single Flask service backed by PostgreSQL. The frontend is served by Flask itself, and uploaded receipts still need persistent disk storage, so a stateless frontend host plus a separate ephemeral backend would be the wrong fit.

### Recommended path: Docker Compose on a VPS
1. Install Docker Engine and the Compose plugin on your server.
2. Copy this repository to the server.
3. Set a strong `SECRET_KEY` in [`docker-compose.yml`](/home/sashank/ExpenSOS/docker-compose.yml) or override it with your deployment environment.
4. Start the service:
   ```bash
   docker compose up -d --build
   ```
5. If you are migrating existing SQLite data, run:
   ```bash
   docker compose exec expensos python backend/migrate_sqlite_to_postgres.py
   ```
6. Visit `http://YOUR_SERVER_IP:6969/login`, or place a reverse proxy such as Nginx/Caddy in front of it for HTTPS.

### What the deployment files do
- [`Dockerfile`](/home/sashank/ExpenSOS/Dockerfile) builds a Python 3.11 image, installs Python dependencies, copies `backend/` and `frontend/`, and starts Gunicorn.
- [`docker-compose.yml`](/home/sashank/ExpenSOS/docker-compose.yml) starts both the Flask app and a PostgreSQL 16 container, and mounts `backend/uploads` so receipt files survive container restarts.
- [`backend/wsgi.py`](/home/sashank/ExpenSOS/backend/wsgi.py) initializes the database on startup and exposes the Flask app to Gunicorn.
- [`backend/migrate_sqlite_to_postgres.py`](/home/sashank/ExpenSOS/backend/migrate_sqlite_to_postgres.py) imports the old SQLite database into PostgreSQL.

### Direct process deployment without Docker
If you prefer a system service instead of containers:
```bash
python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
cd backend
DATABASE_URL='postgresql://USER:PASSWORD@HOST:5432/expensos' SECRET_KEY='replace-me' gunicorn --bind 0.0.0.0:6969 --workers 2 --threads 4 --timeout 120 wsgi:application
```
You should keep PostgreSQL on persistent storage, preserve `backend/uploads`, and put Nginx/Caddy in front of Gunicorn for TLS.

## Next steps you might take
1. Seed the database with more realistic budgets/expenses via `/backend` scripts before sharing the app with others.
2. Wire the unused dependencies (`openai`, `groq`, `google-generativeai`, `pillow`) into future automation or AI-driven insights.
3. Improve the Tailwind pipeline by compiling `frontend/input.css` into a served `.css` file and referencing it from the templates instead of inline styles.

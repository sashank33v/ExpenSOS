# ExpenSOS

ExpenSOS is a self‑hosted personal finance tracker built with Flask, SQLite, and a lean front-end that blends Tailwind-inspired tokens with custom CSS/JS. The project supports authenticated users, expense/budget management, recurring transactions, reminders, receipt uploads, basic insights, and a Chart.js dashboard.

## Getting started
1. Create and activate a Python virtual environment (the repo already includes `venv/` for reference, so you can reuse it or recreate one with `python -m venv venv`).
2. Install the server dependencies with `pip install -r backend/requirements.txt`.
3. Run `python backend/app.py`. The app binds to `http://0.0.0.0:6969` in debug mode.
4. Visit `http://localhost:6969/login`, or register a new account. The seeded admin account is `admin@example.com` / `admin123`.
5. Custom assets (Tailwind CLI, translations, templates) live under `frontend/`; they are served by the Flask backend configured in `backend/app.py`.

## Directory layout
- `backend/`: all Python code that powers the server, including `app.py`, helpers, maintenance scripts, and dependency manifest.
  - `data/expenses.db`: the SQLite database file that Flask opens via an absolute path (`backend/database.py` sets `DB_NAME` accordingly).
  - `uploads/`: receipt images uploaded through the `/add` or `/crud` flows.
  - `patch_templates.py`, `add_svg_sizes.py`, `fix_nav.py`, `fix_svgs.py`, `verify_extraction.py`: CLI utilities that operate on the `frontend/templates`.
- `frontend/`: Jinja2 templates and static assets.
  - `templates/`: page shells (`base.html`, `auth_base.html`) and views for dashboard, expenses, budgets, recurring schedules, reminders, settings, etc.
  - `static/`: the small helper JS and placeholder CSS files that keep chart interactions and keyboard shortcuts working.
  - `input.css` + `tailwind.config.js` + `tailwindcss.exe`: optional Tailwind tooling; the current UI relies on the hand-crafted CSS embedded in `base.html`, but the input file can be compiled if you ever decide to extract the tokens into a bundled stylesheet.

## Key tools & Stack
- **Backend**: Flask handles routing, sessions, flash messaging, JSON APIs, file uploads, and OCR coordination. WerkZuge is used for password hashing and secure filenames.
- **Database**: SQLite stores users, settings, expenses, budgets, recurring items, and reminders. Schema helpers live in `backend/database.py` and include migration-friendly `ALTER TABLE` guards.
- **AI/OCR**: `easyocr` extracts amounts/dates from receipt uploads; `verify_extraction.py` is a standalone script to test that pipeline against images in `backend/uploads`.
- **Frontend**: Jinja2 templates plug into Chart.js for the category dashboard, vanilla JS handles modals/drag-and-drop OCR upload states, and Google Fonts + inline CSS tokens deliver the design system.
- **Tailwind tooling**: `frontend/input.css` defines the Tailwind imports, and `frontend/tailwindconfig.js` configures colors/animations. Use the bundled `frontend/tailwindcss.exe` (or your own Tailwind CLI) to compile if you need a dedicated CSS output.
- **Translations**: `backend/translations.py` keeps English and Hindi copy centralized for reuse across templates.

## Maintenance & utilities
- `backend/patch_templates.py`: cleans up inline Tailwind CDN snippets and patches auth styles inside the frontend templates/input CSS.
- `backend/add_svg_sizes.py`: ensures SVG icons have explicit `width`/`height` attributes so browsers can size them consistently.
- `backend/fix_nav.py` and `backend/fix_svgs.py`: helper scripts to normalize navigation classes and SVG sizing across templates.
- `backend/verify_extraction.py`: reruns the EasyOCR logic from `app.py` so you can experiment with different receipts without running the UI.

## Running & deployment notes
- The Flask app uses `backend/app.py` as the entry point and explicitly sets `template_folder`/`static_folder` to `frontend/` so the reorganized tree works without additional configuration.
- Uploaded files live under `backend/uploads`; confirm that folder is writable by the process running the server to avoid HTTP 500s when saving receipts.
- The SQLite file `backend/data/expenses.db` is created automatically if missing, thanks to `backend/database.py:init_db()`. Keep a backup before truncating data.
- Chart.js is loaded from `https://cdn.jsdelivr.net/npm/chart.js` directly inside `frontend/templates/base.html`.

## Next steps you might take
1. Seed the database with more realistic budgets/expenses via `/backend` scripts before sharing the app with others.
2. Wire the unused dependencies (`openai`, `groq`, `google-generativeai`, `pillow`) into future automation or AI-driven insights.
3. Improve the Tailwind pipeline by compiling `frontend/input.css` into a served `.css` file and referencing it from the templates instead of inline styles.

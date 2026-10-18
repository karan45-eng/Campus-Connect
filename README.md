# CampusConnect — Smart College Improvement Platform

CampusConnect is a Flask web application for college student engagement. It combines an Idea Hub, facility feedback, complaint tracking, polls, notices/events, lost-and-found, educational resource sharing, and an administrator analytics dashboard in one persistent SQLite database.

> **Project status:** The project source, templates, documentation, and automated tests are included. In the build environment used to prepare this folder, Flask and its extensions were not preinstalled and the package index was unreachable. Python syntax checks can be run here, but the Flask application and pytest suite must be executed after installing `requirements.txt` on a machine with package access. Do not treat the application tests as passed until you run them locally.

## Features

- Public student registration, login, logout, secure password hashing, and session-based authentication.
- Initial administrator creation through an interactive Flask CLI command; public registration cannot assign admin access.
- Server-side role checks, ownership checks, CSRF protection, escaped Jinja templates, validation, and safe randomized image filenames.
- Student Idea Hub with search, category/status filters, newest/most-voted sorting, vote toggling, unique vote constraints, and admin-managed status progression.
- Private feedback history, facility ratings, optional anonymous display, admin responses, and moderation.
- Complaint submission and personal tracking; administrators can update priority, status, and resolution notes.
- Poll creation, editing, publication control, opening/closing times, one vote per student, and database-backed result charts.
- Notice creation, publication/archival, search, event dates, and validated registration URLs.
- Lost-and-found listings and resource offers/requests, with ownership-protected updates and status changes.
- Admin dashboard metrics and Chart.js charts based on real database queries (including feedback rating distribution), plus administrative activity logs.
- Optional demo data, added only when you explicitly run `python seed_demo.py`. Existing rows are not updated or deleted.
- Project synopsis and 20 short viva questions in `docs/`.

## Requirements

- Python 3.10 or newer (Python 3.11+ recommended)
- Internet access during the initial `pip install` and for Bootstrap, Bootstrap Icons, and Chart.js CDN assets
- VS Code or another Python editor

## Windows PowerShell setup

Open PowerShell in the `CampusConnect` project folder.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `.env` in a text editor and replace `SECRET_KEY` with a long, random secret. Keep `.env` private and do not commit it. The fallback key in `config.py` is intended only for local development.

If PowerShell blocks virtual-environment activation, run this only for the current PowerShell process, then activate the environment again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

## Initialize the database and create an administrator

The application creates missing database tables automatically on first launch without deleting existing records. These commands are also available explicitly:

```powershell
flask --app app.py init-db
flask --app app.py create-admin
```

The administrator command asks for a name, email, and password. Use at least 12 characters for the administrator password. The command refuses to silently promote an existing account. Public sign-up always creates a student account.

Create a student account through the registration page (`http://127.0.0.1:5000/register`) before trying student features. For a sample set of clearly marked records, run this optional script after registering a student:

```powershell
python seed_demo.py
```

The demo script adds sample records with a `[DEMO]` prefix and does not update or delete existing records.

## Run the application

```powershell
flask --app app.py run --debug
```

Open `http://127.0.0.1:5000` in a browser. Register a student, then log in with the admin account created using the CLI to access the administrator dashboard.

Stop the local server with `Ctrl+C`.

## Run automated tests

```powershell
pytest -q
```

The tests select a separate temporary SQLite file (`campusconnect-pytest.db`) before importing the app and clear only that test database between tests. They cover registration/password hashing, failed login, role permissions, idea submissions and votes, ownership checks, admin idea decisions/logs, feedback privacy and rating validation, complaint resolution, poll vote restrictions, archived notices, lost-and-found, resource status changes, analytics rendering, and record persistence.

## Key files

| File or folder | Purpose |
|---|---|
| `app.py` | Flask routes, authentication, validation, authorization, CLI commands, analytics queries |
| `models.py` | SQLAlchemy database models, constraints, relationships, password methods |
| `extensions.py` | Shared SQLAlchemy and CSRF extensions |
| `config.py` | Secret key, SQLite location, upload limits, session cookie settings |
| `templates/` | Server-rendered HTML pages using Jinja2 |
| `static/css/style.css` | Responsive portal styling and public landing page |
| `static/js/app.js` | Small navigation and destructive-action confirmation helpers |
| `static/uploads/` | Optional user-uploaded images; ignored by Git |
| `instance/campusconnect.db` | Local SQLite database, created on first launch and ignored by Git |
| `tests/test_app.py` | Automated critical-workflow tests |
| `seed_demo.py` | Optional additive sample-data script |
| `docs/PROJECT_SYNOPSIS.md` | Copy-ready synopsis, architecture, modules, schema, limitations |
| `docs/VIVA_QA.md` | Viva preparation questions and concise answers |

## Database design

The database contains `users`, `ideas`, `idea_votes`, `feedback`, `complaints`, `polls`, `poll_options`, `poll_votes`, `notices`, `lost_found_listings`, `resource_listings`, and `activity_logs`. They use primary keys, foreign keys, indexes, and unique vote constraints. SQLite foreign-key enforcement is enabled per connection. Data is stored in the `instance` folder and persists across normal application restarts.

## Important privacy and security notes

- Idea entries are visible to logged-in users to support campus-wide discussion and voting. Only the owner or an administrator can edit/delete eligible submissions.
- Students can see only their own feedback and complaint records. Administrators can access those records for review and resolution.
- Anonymous feedback hides the author in public-facing displays, but the account is retained for authorized administrator access. This is not absolute anonymity.
- Student contact details are not collected or shown in lost-and-found/resource listings.
- CSRF protection applies to state-changing forms. Server-side checks enforce user roles and record ownership.
- Uploaded image files are limited to 2 MB per request, extensions are allow-listed, filenames are randomized, and SVG files are not accepted. A production deployment would additionally use content-based validation and malware scanning.
- The app is intended for local academic demonstration. Before public deployment, configure HTTPS and secure cookies, use a strong secret key, set up database backups, review data retention/access policies, and run production security testing.
- CDN-hosted Bootstrap, Bootstrap Icons, and Chart.js require an internet connection to load. Most pages remain server-rendered; charts need Chart.js to be available.

## Troubleshooting

**`ModuleNotFoundError: No module named 'flask'`** — Activate `.venv` and run `pip install -r requirements.txt`.

**PowerShell cannot activate the virtual environment** — Use the current-process execution-policy command shown in the setup section.

**Charts are blank** — Check the internet connection and browser console; the charts rely on the Chart.js CDN.

**Cannot access `/admin`** — Create an administrator with `flask --app app.py create-admin` and sign in with that account. Registering through the web form intentionally creates a student role only.

**A form says it expired** — Reload the page and submit it again so a fresh CSRF token is used.

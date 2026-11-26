# Forma

Forma is a Django workspace app for notes and documents, with a Notion HTML export importer. It includes user accounts, private workspaces, nested pages, a block editor, autosave, search, favorites, and a responsive workspace UI.

## Install or move to another folder (Windows)

Requires Python 3.12 or newer. To install, copy the project folder to any location and double-click `setup.bat`. It creates a virtual environment inside that folder, installs dependencies, creates or updates the SQLite database, and starts the site at http://127.0.0.1:8000. Create an account in the browser. Stop the server with **Ctrl+C**.

The setup is location independent: copy the source to a new folder and run `setup.bat` there for a fresh installation and fresh database. Do not copy the old `.venv` folder. To carry your existing local data to the new installation, copy both `db.sqlite3` and the `media/` folder; the database contains your pages/accounts and `media/` contains imported images and files. Running `setup.bat` again in the same folder preserves your existing data.

For a Django admin account on a fresh database, run `.venv\Scripts\python.exe manage.py createsuperuser`. Your current `Aravind` account has already been granted Django admin access in the existing database.

## Back up and restore local data

Forma can package the SQLite database and the whole `media/` folder (including Notion imports and profile photos) into one ZIP. The default backup location is `work/backups/`, which is excluded from Git:

```powershell
.venv\Scripts\python.exe manage.py backup_forma
```

You can choose a backup path outside the project so it is easy to copy elsewhere:

```powershell
.venv\Scripts\python.exe manage.py backup_forma --output "D:\FormaBackups\forma-backup.zip"
```

To restore, first stop Forma with **Ctrl+C**. Restore validates the backup checksums and SQLite integrity, creates a safety backup of the current data, and then asks for confirmation before replacing the current database and media files:

```powershell
.venv\Scripts\python.exe manage.py restore_forma "D:\FormaBackups\forma-backup.zip"
```

The restore safety copy is saved in `work/backups/`. Use `--yes` to skip the confirmation prompt while still creating that safety copy. Keep backup ZIPs somewhere private: they contain your pages, accounts, and uploaded files.

SQLite is the default and stores data in `db.sqlite3` beside `manage.py`. No database server or `.env` file is needed for local use. Optional settings can be placed in `.env` (start from `.env.example`).

## Run the tests

Run the core authentication, permissions, autosave, and Notion import regression tests with:

```powershell
.venv\Scripts\python.exe manage.py test pages.tests
```

### Optional PostgreSQL

If PostgreSQL is already installed locally, set these values in `.env`; leaving `DB_HOST` blank keeps SQLite enabled:

```dotenv
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=forma
DB_USER=forma
DB_PASSWORD=your-local-postgres-password
```

Run `setup.bat` again to install/update packages and apply migrations to PostgreSQL. PostgreSQL must be running and the database/user must already exist.

## Deploy with Docker Compose

For a container deployment, create a `.env` file with a random Django secret and a strong database password:

```dotenv
SECRET_KEY=replace-with-a-long-random-value
DEBUG=False
ALLOWED_HOSTS=your-domain.example
CSRF_TRUSTED_ORIGINS=https://your-domain.example
POSTGRES_PASSWORD=replace-with-a-long-random-password
```

Then run `docker compose up --build -d`. Put a TLS reverse proxy in front of port 8000. The web container uses Gunicorn and WhiteNoise; PostgreSQL data persists in a named volume. Back up that volume and use managed object storage and a managed PostgreSQL service for a horizontally scaled deployment.

Create an administrator with `docker compose exec web python manage.py createsuperuser`.

## Notion HTML import

In the sidebar, choose **Import from Notion**. Export your Notion workspace using HTML, then upload either an individual `.html` page or the generated `.zip`. The importer accepts Notion ZIP exports up to 1 GB and up to 500 pages. It follows Notion page-link metadata to rebuild nested pages even when the ZIP is flat, imports linked images and attachments into `media/`, and handles HTML, Markdown, and CSV exports. HTML blocks such as headings, paragraphs, lists, quotes, code, images, links, and tables are converted to editable Forma blocks. Notion-specific database views, formulas, synced blocks, comments, and permissions cannot be recreated from the exported files.

## Current product scope

This is a solid single-workspace foundation, not a full Notion feature clone. The schema supports memberships and viewer/editor roles, but invite management and realtime multi-user editing are not exposed yet. Rich text formatting, database views and formulas, comments, version history, and file upload storage are also follow-up work. Before public launch, add email verification and password reset, a managed media store, backups and restore drills, error monitoring, rate limiting, and automated test coverage.

Production security settings are enabled when `DEBUG=False`; supply a strong `SECRET_KEY`, correct host/origin values, HTTPS, and a managed database. The included Compose file is a convenient single-host deployment starting point.

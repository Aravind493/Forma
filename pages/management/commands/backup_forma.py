"""Create a portable ZIP backup of Forma's SQLite database and media files."""
import hashlib
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.utils import timezone

from pages.backup_utils import BACKUP_VERSION, CHUNK_SIZE, MANIFEST_NAME


class Command(BaseCommand):
    help = "Back up the SQLite database and uploaded media into one ZIP file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            help="Destination ZIP path (defaults to work/backups with a timestamp).",
        )

    def handle(self, *args, **options):
        database_settings = connections["default"].settings_dict
        if database_settings["ENGINE"] != "django.db.backends.sqlite3":
            raise CommandError("Forma backups currently support SQLite only.")

        database_path = Path(database_settings["NAME"])
        if not database_path.is_file():
            raise CommandError(f"SQLite database was not found: {database_path}")

        timestamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        default_output = Path(settings.BASE_DIR) / "work" / "backups" / f"forma-{timestamp}.zip"
        output_path = Path(options["output"]).expanduser() if options["output"] else default_output
        output_path = output_path.resolve()
        if output_path.exists():
            raise CommandError(f"Backup file already exists: {output_path}")

        media_root = Path(settings.MEDIA_ROOT).resolve()
        if output_path == database_path.resolve() or media_root in output_path.parents:
            raise CommandError("Save the backup outside the database and media folders.")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = {
            "format_version": BACKUP_VERSION,
            "created_at": timezone.now().isoformat(),
            "database_engine": "sqlite",
            "files": [],
        }

        try:
            with tempfile.TemporaryDirectory(prefix="forma-backup-") as temp_dir:
                snapshot_path = Path(temp_dir) / "db.sqlite3"
                source_connection = connections["default"]
                source_connection.ensure_connection()
                snapshot = sqlite3.connect(snapshot_path)
                try:
                    source_connection.connection.backup(snapshot)
                finally:
                    snapshot.close()

                with zipfile.ZipFile(
                    output_path,
                    mode="x",
                    compression=zipfile.ZIP_DEFLATED,
                    compresslevel=6,
                ) as archive:
                    self._add_file(archive, snapshot_path, "database/db.sqlite3", manifest)

                    if media_root.exists():
                        for source in sorted(media_root.rglob("*")):
                            if source.is_symlink():
                                continue
                            if not source.is_file():
                                continue
                            relative = source.relative_to(media_root).as_posix()
                            self._add_file(archive, source, f"media/{relative}", manifest)

                    archive.writestr(
                        MANIFEST_NAME,
                        json.dumps(manifest, indent=2, sort_keys=True),
                    )
        except (OSError, sqlite3.Error, zipfile.BadZipFile) as error:
            output_path.unlink(missing_ok=True)
            raise CommandError(f"Could not create the backup: {error}") from error

        self.stdout.write(self.style.SUCCESS(f"Backup created: {output_path}"))
        self.stdout.write(f"Included {len(manifest['files']) - 1} media files and the SQLite database.")

    @staticmethod
    def _add_file(archive, source, archive_name, manifest):
        digest = hashlib.sha256()
        size = 0
        with source.open("rb") as input_file, archive.open(archive_name, "w") as output_file:
            while True:
                chunk = input_file.read(CHUNK_SIZE)
                if not chunk:
                    break
                output_file.write(chunk)
                digest.update(chunk)
                size += len(chunk)

        manifest["files"].append({
            "path": archive_name,
            "size": size,
            "sha256": digest.hexdigest(),
        })

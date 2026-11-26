"""Safely restore a Forma database-and-media backup created by backup_forma."""
import shutil
import uuid
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from pages.backup_utils import extract_validated_backup


class Command(BaseCommand):
    help = "Restore SQLite and media from a Forma backup ZIP."

    def add_arguments(self, parser):
        parser.add_argument("backup", help="Path to a ZIP created by backup_forma.")
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip the confirmation prompt (still creates a safety backup first).",
        )

    def handle(self, *args, **options):
        database_settings = connections["default"].settings_dict
        if database_settings["ENGINE"] != "django.db.backends.sqlite3":
            raise CommandError("Forma restore currently supports SQLite only.")

        backup_path = Path(options["backup"]).expanduser().resolve()
        if not backup_path.is_file():
            raise CommandError(f"Backup file was not found: {backup_path}")

        database_path = Path(database_settings["NAME"]).resolve()
        media_root = Path(settings.MEDIA_ROOT).resolve()
        if not options["yes"]:
            answer = input(
                "This replaces the current database and all files in MEDIA_ROOT. "
                "A safety backup will be created first. Continue? [y/N] "
            ).strip().lower()
            if answer not in {"y", "yes"}:
                self.stdout.write("Restore cancelled. Current data was not changed.")
                return

        staging_root = Path(settings.BASE_DIR) / "work" / f"restore-{uuid.uuid4().hex}"
        staged_backup = staging_root / "validated"
        old_media = staging_root / "previous-media"
        staged_database = staging_root / "replacement.sqlite3"
        backup_folder = Path(settings.BASE_DIR) / "work" / "backups"
        safety_backup = backup_folder / f"pre-restore-{uuid.uuid4().hex}.zip"
        database_replaced = False
        media_moved = False
        media_touched = False
        preserve_staging = False

        try:
            staging_root.mkdir(parents=True, exist_ok=False)
            try:
                backup_database, backup_media = extract_validated_backup(backup_path, staged_backup)
            except (OSError, ValueError, KeyError, RuntimeError, zipfile.BadZipFile) as error:
                raise CommandError(f"Backup validation failed: {error}") from error

            self.stdout.write("Creating a safety backup of the current data…")
            call_command("backup_forma", output=str(safety_backup), stdout=self.stdout)

            staged_database.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_database, staged_database)
            media_root.parent.mkdir(parents=True, exist_ok=True)
            connections.close_all()

            if media_root.exists():
                media_root.rename(old_media)
                media_moved = True
            media_touched = True
            if backup_media.exists():
                shutil.copytree(backup_media, media_root)
            else:
                media_root.mkdir(parents=True, exist_ok=True)

            staged_database.replace(database_path)
            database_replaced = True
        except CommandError:
            raise
        except OSError as error:
            if not database_replaced:
                try:
                    if media_touched and media_root.exists():
                        shutil.rmtree(media_root)
                    if media_moved and old_media.exists():
                        old_media.rename(media_root)
                except OSError as rollback_error:
                    preserve_staging = True
                    raise CommandError(
                        f"Restore failed and media rollback also failed: {rollback_error}. "
                        f"Your previous media is preserved at {old_media}; "
                        f"the safety backup is at {safety_backup}."
                    ) from error
            raise CommandError(
                f"Restore could not be completed: {error}. "
                f"Current data is protected by {safety_backup}."
            ) from error
        finally:
            if not preserve_staging:
                shutil.rmtree(staging_root, ignore_errors=True)

        shutil.rmtree(old_media, ignore_errors=True)
        self.stdout.write(self.style.SUCCESS("Restore completed."))
        self.stdout.write(f"Database restored to: {database_path}")
        self.stdout.write(f"Imported files restored to: {media_root}")
        self.stdout.write(f"Safety backup kept at: {safety_backup}")

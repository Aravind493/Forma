"""Helpers for validating and extracting Forma data backups."""
import hashlib
import json
import sqlite3
import stat
import zipfile
from pathlib import Path, PurePosixPath


MANIFEST_NAME = "manifest.json"
BACKUP_VERSION = 1
CHUNK_SIZE = 1024 * 1024


def _safe_archive_path(name):
    if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
        raise ValueError("The backup contains an unsafe file path.")

    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("The backup contains an unsafe file path.")
    if path.as_posix() != name:
        raise ValueError("The backup contains a non-canonical file path.")

    if path.as_posix() != "database/db.sqlite3" and not name.startswith("media/"):
        raise ValueError("The backup contains an unexpected file.")
    if name.startswith("media/") and len(path.parts) < 2:
        raise ValueError("The backup contains an invalid media path.")
    return path


def extract_validated_backup(archive_path, destination):
    """Validate the manifest, hashes, paths, and SQLite file before returning staged files."""
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("The backup contains duplicate file entries.")

        try:
            manifest_info = archive.getinfo(MANIFEST_NAME)
        except KeyError as error:
            raise ValueError("The backup is missing its manifest.") from error
        if manifest_info.file_size > 5 * 1024 * 1024:
            raise ValueError("The backup manifest is unexpectedly large.")
        manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
        if manifest.get("format_version") != BACKUP_VERSION:
            raise ValueError("This backup format version is not supported.")

        records = manifest.get("files")
        if not isinstance(records, list):
            raise ValueError("The backup manifest is invalid.")

        expected = {}
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("The backup manifest contains an invalid file record.")
            name = record.get("path")
            _safe_archive_path(name)
            if name in expected:
                raise ValueError("The backup manifest contains duplicate file records.")
            size = record.get("size")
            digest = record.get("sha256")
            if not isinstance(size, int) or size < 0:
                raise ValueError("The backup manifest contains an invalid file size.")
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError("The backup manifest contains an invalid checksum.")
            expected[name] = record

        if "database/db.sqlite3" not in expected:
            raise ValueError("The backup does not contain the SQLite database.")

        archive_files = set(names) - {MANIFEST_NAME}
        if archive_files != set(expected):
            raise ValueError("The backup file list does not match its manifest.")

        for info in infos:
            name = info.filename
            if name == MANIFEST_NAME:
                continue
            relative = _safe_archive_path(name)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("The backup contains a symbolic link.")

            record = expected[name]
            if info.file_size != record["size"]:
                raise ValueError(f"The size check failed for {name}.")

            target = (destination / Path(*relative.parts)).resolve()
            if destination != target and destination not in target.parents:
                raise ValueError("The backup contains a path outside its extraction folder.")
            target.parent.mkdir(parents=True, exist_ok=True)

            digest = hashlib.sha256()
            written = 0
            with archive.open(info) as source, target.open("wb") as output:
                while True:
                    chunk = source.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
                    written += len(chunk)

            if written != record["size"] or digest.hexdigest() != record["sha256"]:
                raise ValueError(f"The checksum check failed for {name}.")

    database_path = destination / "database" / "db.sqlite3"
    database = None
    try:
        database = sqlite3.connect(database_path)
        integrity = database.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.DatabaseError as error:
        raise ValueError("The backup database could not be opened.") from error
    finally:
        if database is not None:
            database.close()

    if not integrity or integrity[0] != "ok":
        raise ValueError("The backup database failed SQLite's integrity check.")

    return database_path, destination / "media"

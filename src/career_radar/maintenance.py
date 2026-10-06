"""本地数据备份与维护操作。所有产物留在项目私有目录。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .output import prune_expired_reports
from .storage import JobStorage
from .web_repository import WebRepository


class LocalMaintenance:
    """以一个 ``run`` interface 封装本地维护细节和安全约束。"""

    def __init__(self, repository: WebRepository, config_file: Path) -> None:
        self.repository = repository
        self.config_file = config_file.resolve()

    def list_backups(self) -> list[dict[str, Any]]:
        """只返回非敏感元数据；不会返回目录、内容或清单详情。"""

        backup_dir = self._backup_dir(create=False)
        if not backup_dir.is_dir():
            return []
        timezone = ZoneInfo(self.repository.settings.app.timezone)
        result = []
        for path in self._backup_files(backup_dir):
            stat = path.stat()
            try:
                created_at = datetime.strptime(
                    path.name.removeprefix("career-radar-backup-").removesuffix(".zip"),
                    "%Y%m%d-%H%M%S-%f",
                ).replace(tzinfo=timezone).isoformat(timespec="seconds")
            except ValueError:
                created_at = datetime.fromtimestamp(stat.st_mtime, timezone).isoformat(
                    timespec="seconds"
                )
            included_files: int | None = None
            status = "unchecked"
            try:
                with zipfile.ZipFile(path) as archive:
                    included_files = len(
                        [name for name in archive.namelist() if name != "manifest.json"]
                    )
            except (OSError, ValueError, zipfile.BadZipFile):
                status = "invalid"
            result.append(
                {
                    "name": path.name,
                    "createdAt": created_at,
                    "sizeBytes": stat.st_size,
                    "includedFiles": included_files,
                    "integrityStatus": status,
                }
            )
        return result

    def verify_backup(self, backup_name: str) -> dict[str, Any]:
        """校验 ZIP、逐文件哈希与其中的 SQLite 一致性快照。"""

        path = self._existing_backup_path(backup_name)
        checked_files = 0
        database_status = "not_present"
        try:
            with zipfile.ZipFile(path) as archive:
                bad_member = archive.testzip()
                if bad_member is not None:
                    raise ValueError("ZIP 数据校验失败")
                manifest = json.loads(archive.read("manifest.json"))
                included = manifest.get("included")
                if not isinstance(included, list) or not all(
                    isinstance(name, str) for name in included
                ):
                    raise ValueError("备份清单格式无效")
                archive_names = set(archive.namelist())
                if any(name not in archive_names for name in included):
                    raise ValueError("备份清单与 ZIP 内容不一致")
                checksums = manifest.get("sha256")
                if checksums is not None:
                    if not isinstance(checksums, dict):
                        raise ValueError("备份哈希清单格式无效")
                    for name in included:
                        expected = checksums.get(name)
                        if not isinstance(expected, str):
                            raise ValueError("备份哈希清单不完整")
                        with archive.open(name) as source:
                            actual = self._sha256_stream(source)
                        if actual != expected:
                            raise ValueError("备份文件哈希校验失败")
                checked_files = len(included)
                database_entry = manifest.get("databaseEntry")
                if database_entry is None:
                    database_entry = next(
                        (
                            name
                            for name in included
                            if name.startswith("data/")
                            and name.casefold().endswith((".db", ".sqlite", ".sqlite3"))
                        ),
                        None,
                    )
                if database_entry is not None:
                    if database_entry not in archive_names:
                        raise ValueError("数据库快照未包含在备份中")
                    self._verify_database_member(archive, database_entry)
                    database_status = "ok"
        except (
            OSError,
            KeyError,
            sqlite3.DatabaseError,
            zipfile.BadZipFile,
            json.JSONDecodeError,
            ValueError,
        ) as exc:
            return {
                "ok": False,
                "name": backup_name,
                "integrityStatus": "invalid",
                "checkedFiles": checked_files,
                "databaseIntegrity": database_status,
                "message": str(exc) if isinstance(exc, ValueError) else "备份文件无法读取",
            }
        return {
            "ok": True,
            "name": backup_name,
            "integrityStatus": "valid",
            "checkedFiles": checked_files,
            "databaseIntegrity": database_status,
            "message": "备份完整性校验通过",
        }

    def delete_backup(self, backup_name: str) -> dict[str, Any]:
        path = self._existing_backup_path(backup_name)
        path.unlink()
        return {"ok": True, "name": backup_name, "message": "本地备份已删除"}

    def run(self, action: str) -> dict[str, Any]:
        handlers = {
            "export": self._create_backup,
            "clearLogs": self._clear_logs,
            "rebuildIndex": self._rebuild_index,
            "recalcMatch": self._recalculate_match,
            "cleanReports": self._clean_reports,
        }
        try:
            handler = handlers[action]
        except KeyError as exc:
            raise ValueError("未知维护操作") from exc
        return handler()

    def _rebuild_index(self) -> dict[str, Any]:
        settings = self.repository.settings
        JobStorage(settings.app.database_path).reset_job_embeddings()
        with self.repository.transaction() as connection:
            connection.execute("REINDEX")
        return {"ok": True, "message": "SQLite 索引与语义向量已重建"}

    @staticmethod
    def _recalculate_match() -> dict[str, Any]:
        return {"ok": True, "message": "新画像将在下一次真实扫描中生效"}

    def _clear_logs(self) -> dict[str, Any]:
        cleared = 0
        for path in self.repository.settings.app.log_dir.glob("*.log*"):
            if path.is_file() and not path.is_symlink():
                path.write_text("", encoding="utf-8")
                cleared += 1
        return {"ok": True, "message": f"已清空 {cleared} 个运行日志文件", "cleared": cleared}

    def _clean_reports(self) -> dict[str, Any]:
        settings = self.repository.settings
        today = datetime.now(ZoneInfo(settings.app.timezone)).date()
        removed = prune_expired_reports(
            settings.app.output_dir,
            settings.app.report_retention_days,
            today=today,
        )
        return {
            "ok": True,
            "message": (
                f"已清理 {removed} 个超过 {settings.app.report_retention_days} 天的日报文件"
            ),
            "removed": removed,
        }

    def _create_backup(self) -> dict[str, Any]:
        settings = self.repository.settings
        backup_dir = self._backup_dir(create=True)
        timestamp = datetime.now(ZoneInfo(settings.app.timezone)).strftime(
            "%Y%m%d-%H%M%S-%f"
        )
        backup_name = f"career-radar-backup-{timestamp}.zip"
        destination = backup_dir / backup_name
        temporary_zip = backup_dir / f".{backup_name}.tmp"
        database_snapshot: Path | None = None
        included: list[str] = []
        checksums: dict[str, str] = {}
        seen: set[Path] = set()
        database_entry: str | None = None

        try:
            with zipfile.ZipFile(
                temporary_zip,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            ) as archive:
                self._add_file(
                    archive,
                    self.config_file,
                    "config/config.yaml",
                    included,
                    checksums,
                    seen,
                )
                self._add_file(
                    archive,
                    settings.app.company_catalog_path,
                    f"data/{settings.app.company_catalog_path.name}",
                    included,
                    checksums,
                    seen,
                )
                if settings.app.database_path.is_file():
                    database_snapshot = self._snapshot_database(
                        settings.app.database_path,
                        backup_dir,
                    )
                    database_entry = f"data/{settings.app.database_path.name}"
                    self._add_file(
                        archive,
                        database_snapshot,
                        database_entry,
                        included,
                        checksums,
                        seen,
                    )
                self._add_tree(
                    archive,
                    settings.app.output_dir,
                    "output",
                    included,
                    checksums,
                    seen,
                    excluded_roots=(backup_dir,),
                )
                self._add_tree(
                    archive,
                    settings.app.log_dir,
                    "logs",
                    included,
                    checksums,
                    seen,
                    excluded_roots=(backup_dir,),
                )
                self._add_file(
                    archive,
                    settings.application.profile_path,
                    "private/application_profile.yaml",
                    included,
                    checksums,
                    seen,
                )
                self._add_tree(
                    archive,
                    settings.application.output_dir,
                    "private/application_outputs",
                    included,
                    checksums,
                    seen,
                    excluded_roots=(backup_dir,),
                )
                manifest = {
                    "createdAt": datetime.now(
                        ZoneInfo(settings.app.timezone)
                    ).isoformat(timespec="seconds"),
                    "included": included,
                    "sha256": checksums,
                    "databaseEntry": database_entry,
                    "excluded": [
                        ".env",
                        "system environment variables",
                        "existing private/backups archives",
                    ],
                }
                archive.writestr(
                    "manifest.json",
                    json.dumps(manifest, ensure_ascii=False, indent=2),
                )
            os.replace(temporary_zip, destination)
        finally:
            if database_snapshot is not None and database_snapshot.exists():
                database_snapshot.unlink()
            if temporary_zip.exists():
                temporary_zip.unlink()

        verification = self.verify_backup(backup_name)
        if not verification["ok"]:
            raise RuntimeError("新建备份未通过完整性校验，原有备份仍保留")
        pruned = self._prune_backups(settings.app.backup_retention_count)
        return {
            "ok": True,
            "message": f"本地备份已创建：{backup_name}",
            "backupName": backup_name,
            "includedFiles": len(included),
            "sizeBytes": destination.stat().st_size,
            "prunedBackups": pruned,
        }

    def _backup_dir(self, *, create: bool) -> Path:
        project_root = self.config_file.parent.resolve()
        private_dir = project_root / "private"
        backup_dir = private_dir / "backups"
        if private_dir.is_symlink() or backup_dir.is_symlink():
            raise RuntimeError("备份目录不得使用符号链接")
        if not private_dir.resolve().is_relative_to(project_root):
            raise RuntimeError("备份目录必须位于项目 private 目录内")
        if not backup_dir.resolve().is_relative_to(project_root):
            raise RuntimeError("备份目录必须位于项目 private 目录内")
        if create:
            backup_dir.mkdir(parents=True, exist_ok=True)
        resolved = backup_dir.resolve()
        if not resolved.is_relative_to(project_root):
            raise RuntimeError("备份目录必须位于项目 private 目录内")
        return resolved

    @staticmethod
    def _backup_files(backup_dir: Path) -> list[Path]:
        paths = [
            path
            for path in backup_dir.glob("career-radar-backup-*.zip")
            if path.is_file()
            and not path.is_symlink()
            and re.fullmatch(
                r"career-radar-backup-\d{8}-\d{6}-\d{6}\.zip",
                path.name,
            )
        ]
        return sorted(paths, key=lambda path: path.name, reverse=True)

    def _existing_backup_path(self, backup_name: str) -> Path:
        if not re.fullmatch(
            r"career-radar-backup-\d{8}-\d{6}-\d{6}\.zip",
            backup_name,
        ):
            raise ValueError("备份文件名无效")
        backup_dir = self._backup_dir(create=False)
        path = backup_dir / backup_name
        if not path.is_file() or path.is_symlink() or path.resolve().parent != backup_dir:
            raise FileNotFoundError(backup_name)
        return path

    def _prune_backups(self, retention_count: int) -> int:
        backup_dir = self._backup_dir(create=False)
        removed = 0
        for path in self._backup_files(backup_dir)[retention_count:]:
            path.unlink()
            removed += 1
        return removed

    @staticmethod
    def _sha256_stream(source: Any) -> str:
        digest = hashlib.sha256()
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _verify_database_member(archive: zipfile.ZipFile, member: str) -> None:
        handle = tempfile.NamedTemporaryFile(
            prefix="career-radar-verify-",
            suffix=".sqlite",
            delete=False,
        )
        snapshot = Path(handle.name)
        try:
            with handle, archive.open(member) as source:
                shutil.copyfileobj(source, handle)
            uri = f"file:{snapshot.resolve().as_posix()}?mode=ro"
            with closing(sqlite3.connect(uri, uri=True)) as connection:
                rows = connection.execute("PRAGMA integrity_check").fetchall()
            if rows != [("ok",)]:
                raise ValueError("数据库快照完整性校验失败")
        finally:
            snapshot.unlink(missing_ok=True)

    @staticmethod
    def _snapshot_database(database_path: Path, backup_dir: Path) -> Path:
        handle = tempfile.NamedTemporaryFile(
            prefix=".career-radar-db-",
            suffix=".sqlite",
            dir=backup_dir,
            delete=False,
        )
        snapshot = Path(handle.name)
        handle.close()
        source_uri = f"file:{database_path.resolve().as_posix()}?mode=ro"
        try:
            with closing(sqlite3.connect(source_uri, uri=True)) as source:
                with closing(sqlite3.connect(snapshot)) as target:
                    source.backup(target)
        except Exception:
            snapshot.unlink(missing_ok=True)
            raise
        return snapshot

    @staticmethod
    def _add_file(
        archive: zipfile.ZipFile,
        source: Path,
        archive_name: str,
        included: list[str],
        checksums: dict[str, str],
        seen: set[Path],
    ) -> None:
        if not source.is_file() or source.is_symlink():
            return
        resolved = source.resolve()
        if resolved in seen:
            return
        digest = hashlib.sha256()
        with resolved.open("rb") as original, archive.open(archive_name, "w") as target:
            while chunk := original.read(1024 * 1024):
                target.write(chunk)
                digest.update(chunk)
        included.append(archive_name)
        checksums[archive_name] = digest.hexdigest()
        seen.add(resolved)

    @classmethod
    def _add_tree(
        cls,
        archive: zipfile.ZipFile,
        root: Path,
        archive_root: str,
        included: list[str],
        checksums: dict[str, str],
        seen: set[Path],
        *,
        excluded_roots: tuple[Path, ...] = (),
    ) -> None:
        if not root.is_dir() or root.is_symlink():
            return
        resolved_root = root.resolve()
        resolved_exclusions = tuple(path.resolve() for path in excluded_roots)
        for source in sorted(root.rglob("*")):
            if not source.is_file() or source.is_symlink():
                continue
            resolved = source.resolve()
            if (
                not resolved.is_relative_to(resolved_root)
                or source.name == ".env"
                or any(
                    resolved == excluded or resolved.is_relative_to(excluded)
                    for excluded in resolved_exclusions
                )
            ):
                continue
            relative = resolved.relative_to(resolved_root).as_posix()
            cls._add_file(
                archive,
                resolved,
                f"{archive_root}/{relative}",
                included,
                checksums,
                seen,
            )

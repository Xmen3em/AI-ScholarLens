"""Binary-safe Compose PostgreSQL backup and isolated, non-overwriting restore drill."""

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

FINGERPRINT_SQL = """
SELECT json_build_object(
    'papers', (SELECT count(*) FROM papers),
    'content_md5', (SELECT md5(coalesce(string_agg(row_to_json(p)::text, '' ORDER BY arxiv_id), '')) FROM papers p),
    'schema_revision', (SELECT string_agg(version_num, ',' ORDER BY version_num) FROM alembic_version)
);
"""


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class Recovery:
    def __init__(self, wsl: str | None = None):
        self.prefix = (["wsl.exe", "-d", wsl, "--"] if wsl else []) + ["docker", "compose", "exec", "-T", "postgres"]

    def run(self, args: list[str], *, output=None, input_stream=None) -> bytes:
        # Do not send binary archives through PowerShell text redirection.
        result = subprocess.run(self.prefix + args, stdin=input_stream, stdout=output or subprocess.PIPE,
                                stderr=subprocess.PIPE, check=True)
        return result.stdout or b""

    def fingerprint(self, database: str) -> dict:
        raw = self.run(["psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-U", "rag_user", "-d", database,
                        "-c", FINGERPRINT_SQL])
        return json.loads(raw)

    def create(self, directory: Path) -> dict:
        directory.mkdir(parents=True, exist_ok=False)
        before = self.fingerprint("rag_db")
        path = directory / "database.dump"
        with path.open("xb") as output:
            self.run(["pg_dump", "-U", "rag_user", "-d", "rag_db", "--format=custom"], output=output)
        after = self.fingerprint("rag_db")
        if before != after:
            raise ValueError("Source paper fingerprint changed during backup; retry in a new directory")
        manifest = {"created_utc": datetime.now(timezone.utc).isoformat(), "source_database": "rag_db",
                    "source": before, "sha256": checksum(path)}
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest

    def drill(self, directory: Path) -> dict:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        path = directory / "database.dump"
        if checksum(path) != manifest["sha256"]:
            raise ValueError("Archive checksum mismatch")
        report_path = directory / "restore-drill.json"
        if report_path.exists():
            raise FileExistsError("Restore report already exists; preserve it and use a new backup directory")
        target = f"scholarlens_restore_{uuid4().hex}"
        self.run(["createdb", "-U", "rag_user", "--template=template0", target])
        try:
            # Feed bytes directly to pg_restore via stdin; no shell, no --clean, no
            # user-supplied target. This cannot overwrite an existing database.
            with path.open("rb") as archive:
                self.run(["pg_restore", "-U", "rag_user", "-d", target,
                          "--single-transaction", "--exit-on-error", "--no-owner", "--no-acl"], input_stream=archive)
            restored = self.fingerprint(target)
            report = {"target": target, "restored": restored, "source": manifest["source"],
                      "matched": restored == manifest["source"], "archive_sha256": manifest["sha256"]}
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            if not report["matched"]:
                raise ValueError("Restored paper fingerprint differs from the backup")
            return report
        finally:
            self.run(["psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "rag_user", "-d", "postgres",
                      "-c", f'DROP DATABASE "{target}"'])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("create", "drill"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--wsl", help="Windows only: Docker runs through this WSL distribution")
    args = parser.parse_args()
    recovery = Recovery(args.wsl)
    try:
        result = recovery.create(args.directory) if args.action == "create" else recovery.drill(args.directory)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"Recovery operation failed ({type(exc).__name__}); existing databases were not overwritten.")
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

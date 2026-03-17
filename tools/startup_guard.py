from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import sys


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BACKUP_DIR = ROOT / "backups" / "startup-guard"
KEEP_ARCHIVES = 10
ROUTES = [
    "/",
    "/stocks",
    "/stocks/FTAI",
    "/transcripts",
    "/ai",
    "/exports",
    "/search",
    "/trash",
    "/monitor",
    "/signals",
    "/stocks/calendar",
]
SNAPSHOT_TARGETS = [
    "app.py",
    "start.bat",
    "README.md",
    "requirements.txt",
    "monitor_runner.py",
    "signal_monitor_runner.py",
    "oss_client.py",
    "tingwu_client.py",
    "templates",
    "static",
]


def build_snapshot() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = BACKUP_DIR / f"startup_guard_{timestamp}.zip"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for name in SNAPSHOT_TARGETS:
            source = ROOT / name
            if not source.exists():
                continue
            if source.is_file():
                archive.write(source, source.relative_to(ROOT))
                continue
            for item in source.rglob("*"):
                if item.is_file():
                    archive.write(item, item.relative_to(ROOT))
    archives = sorted(BACKUP_DIR.glob("startup_guard_*.zip"), key=lambda path: path.stat().st_mtime)
    for stale in archives[:-KEEP_ARCHIVES]:
        stale.unlink(missing_ok=True)
    return archive_path


def run_smoke_check() -> list[tuple[str, int]]:
    from app import app

    client = app.test_client()
    results: list[tuple[str, int]] = []
    for route in ROUTES:
        response = client.get(route, follow_redirects=True)
        results.append((route, response.status_code))
    return results


def main() -> int:
    snapshot_path = build_snapshot()
    print(f"[startup-guard] 已创建保护快照: {snapshot_path}")
    results = run_smoke_check()
    failures = [(route, status) for route, status in results if status >= 500]
    for route, status in results:
        print(f"[startup-guard] {route} -> {status}")
    if failures:
        print("[startup-guard] 启动前体检失败，已阻止启动。", file=sys.stderr)
        for route, status in failures:
            print(f"  - {route}: {status}", file=sys.stderr)
        return 1
    print("[startup-guard] 体检通过，可以启动网页。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

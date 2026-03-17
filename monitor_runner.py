from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


REPORT_SUFFIXES = {".md", ".markdown"}
PREVIOUS_REPORT_MAX_CHARS = 12_000
DEFAULT_TIMEOUT_SECONDS = 900


@dataclass
class RunnerConfig:
    stock_pool: list[str]
    codex_path: str
    workdir: str
    timeout_seconds: int
    output_dir: Path
    prompt_dir: Path
    log_dir: Path
    trigger: str
    run_id: str
    meta_path: Path
    runtime_path: Path | None


def beijing_now() -> datetime:
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo("Asia/Shanghai"))
    return datetime.now(timezone(timedelta(hours=8)))


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_runtime_status(meta_status: str) -> str:
    normalized = str(meta_status or "").strip().lower()
    if normalized == "success":
        return "completed"
    if normalized in {"timeout"}:
        return "timeout"
    if normalized in {"failed", "error"}:
        return "failed"
    return normalized or "idle"


def sync_runtime_snapshot(
    runtime_path: Path | None,
    *,
    run_id: str,
    stock_pool: list[str],
    meta: dict[str, Any],
    meta_path: Path,
) -> None:
    if runtime_path is None:
        return

    current = load_json(runtime_path)
    current_run_id = str(current.get("run_id") or "").strip()
    if current_run_id and run_id and current_run_id != run_id:
        return

    report_path = str(meta.get("report_path") or current.get("report_path") or "").strip()
    runtime_status = resolve_runtime_status(str(meta.get("status") or ""))
    current.update(
        {
            "run_id": run_id or current_run_id,
            "status": runtime_status,
            "pid": 0,
            "stock_pool": stock_pool,
            "started_at": str(current.get("started_at") or meta.get("started_at") or "").strip(),
            "finished_at": str(meta.get("finished_at") or current.get("finished_at") or "").strip(),
            "report_path": report_path,
            "report_filename": Path(report_path).name if report_path else "",
            "meta_path": str(meta_path),
            "stdout_path": str(current.get("stdout_path") or meta.get("stdout_log_path") or "").strip(),
            "stderr_path": str(current.get("stderr_path") or meta.get("stderr_log_path") or "").strip(),
            "message": "监测结果已写入报告目录。" if runtime_status == "completed" else "",
            "error": str(meta.get("error_message") or "").strip(),
            "termination_requested": False,
        }
    )
    save_json(runtime_path, current)


def parse_stock_pool(text: str) -> list[str]:
    seen: set[str] = set()
    symbols: list[str] = []
    for chunk in re.split(r"[\s,;；]+", text.strip()):
        candidate = re.sub(r"[^A-Z0-9.\-]", "", chunk.strip().upper().lstrip("$"))
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        symbols.append(candidate)
    return symbols


def read_report_text(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def is_monitor_report_path(path: Path) -> bool:
    if path.suffix.lower() not in REPORT_SUFFIXES or not path.is_file():
        return False
    lowered_name = path.name.lower()
    if "manual_run" in lowered_name or "auto_0700" in lowered_name:
        return True
    try:
        head = read_report_text(path)[:160]
    except OSError:
        return False
    return "# Stock Monitor Report" in head or "Stock Monitor Report" in head


def latest_previous_report(output_dir: Path) -> Path | None:
    candidates = [path for path in output_dir.iterdir() if is_monitor_report_path(path)]
    if not candidates:
        return None
    candidates.sort(key=lambda item: item.stat().st_mtime_ns, reverse=True)
    return candidates[0]


def read_previous_report_excerpt(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    try:
        text = read_report_text(path)
    except OSError:
        return ""
    return text[-PREVIOUS_REPORT_MAX_CHARS:]


def build_prompt(stock_pool: list[str], trigger: str, created_at: str, previous_excerpt: str) -> str:
    previous_report_text = previous_excerpt if previous_excerpt else "No previous report."
    stock_pool_text = ", ".join(stock_pool)
    return f"""
You are a market-monitoring analyst. Use live web search if available.
Write the final report in Simplified Chinese.

Current Beijing time: {created_at}
Trigger: {trigger}
Stock pool: {stock_pool_text}

Task requirements:
1. Search each stock in the pool for newly emerged developments and newly active public discussions.
2. Prioritize official filings, investor relations pages, mainstream media, and public discussion sources such as X, Reddit, Stocktwits, and forums.
3. Prefer the last 24 hours. If there is not enough signal, widen to the last 7 days and say so explicitly.
4. Separate verified facts from rumors, public debate, and sentiment.
5. Compare against the previous report excerpt and focus only on what is actually new, changed, intensified, reversed, or fading.
6. For each stock, include:
- one-line conclusion
- new verified facts
- new discussion or sentiment shifts
- change vs previous report
- possible impact on earnings, valuation, catalyst, risk, or sentiment
- sources with date and URL
7. If there is no material update for a stock, say so clearly.
8. Do not invent sources.

Output format:
# Stock Monitor Report
## Run Summary
- Trigger:
- Stock pool:
- Comparison baseline:

## Top Changes

## Per Stock
### TICKER
- One-line conclusion:
- New verified facts:
- New discussion or sentiment:
- Change vs previous report:
- Potential impact:
- Sources:

## Follow-up Questions

Previous report excerpt:
<<<PREVIOUS_REPORT
{previous_report_text}
PREVIOUS_REPORT>>>
""".strip()


def discover_codex_path(preferred: str = "") -> str | None:
    candidates: list[Path] = []

    if preferred:
        preferred_path = Path(preferred)
        if preferred_path.exists():
            return str(preferred_path)
        preferred_which = shutil.which(preferred)
        if preferred_which:
            return preferred_which

    system_which = shutil.which("codex")
    if system_which:
        return system_which

    vscode_extensions = Path.home() / ".vscode" / "extensions"
    if vscode_extensions.exists():
        candidates.extend(
            sorted(
                vscode_extensions.glob("openai.chatgpt-*/bin/windows-x86_64/codex.exe"),
                reverse=True,
            )
        )
        candidates.extend(
            sorted(
                vscode_extensions.glob("openai.chatgpt-*/bin/windows-arm64/codex.exe"),
                reverse=True,
            )
        )

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return None


def resolve_codex_path(preferred: str) -> str:
    found = discover_codex_path(preferred)
    if found:
        return found
    raise FileNotFoundError("Could not find codex.exe. Checked PATH and the local VS Code extension directory.")


def check_codex_login(codex_path: str) -> None:
    result = subprocess.run(
        [codex_path, "login", "status"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0 or "Logged in" not in output:
        raise RuntimeError("Codex is not logged in. Run `codex login` first.")


def write_failure_report(report_path: Path, reason: str, *, trigger: str, created_at: str, stock_pool: list[str]) -> None:
    report_path.write_text(
        (
            "# Stock Monitor Report\n\n"
            f"- Trigger: `{trigger}`\n"
            f"- Run time: {created_at}\n"
            f"- Stock pool: `{', '.join(stock_pool)}`\n"
            "- Result: failed\n\n"
            "Reason:\n"
            f"{reason}\n"
        ),
        encoding="utf-8",
    )


def build_report_stem(created_at: str, trigger: str) -> str:
    timestamp = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").strftime("%Y%m%d_%H%M%S")
    return f"{timestamp}_{trigger}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one manual Stock Monitor task for the web workspace.")
    parser.add_argument("--stocks", required=True, help="Semicolon/comma separated stock symbols.")
    parser.add_argument("--codex-path", default="codex")
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--prompt-dir", required=True)
    parser.add_argument("--log-dir", required=True)
    parser.add_argument("--trigger", default="manual_run")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--meta-path", required=True)
    parser.add_argument("--runtime-path", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stock_pool = parse_stock_pool(args.stocks)
    if not stock_pool:
        raise SystemExit("Stock pool cannot be empty.")

    output_dir = Path(args.output_dir)
    prompt_dir = Path(args.prompt_dir)
    log_dir = Path(args.log_dir)
    meta_path = Path(args.meta_path)
    runtime_path = Path(args.runtime_path) if args.runtime_path else None
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    config = RunnerConfig(
        stock_pool=stock_pool,
        codex_path=args.codex_path,
        workdir=args.workdir,
        timeout_seconds=max(120, int(args.timeout_seconds or DEFAULT_TIMEOUT_SECONDS)),
        output_dir=output_dir,
        prompt_dir=prompt_dir,
        log_dir=log_dir,
        trigger=args.trigger,
        run_id=args.run_id,
        meta_path=meta_path,
        runtime_path=runtime_path,
    )

    created_at = beijing_now().strftime("%Y-%m-%d %H:%M:%S")
    stem = build_report_stem(created_at, config.trigger)
    report_path = config.output_dir / f"{stem}.md"
    prompt_path = config.prompt_dir / f"{stem}.txt"
    stdout_log_path = config.log_dir / f"{stem}.stdout.log"
    stderr_log_path = config.log_dir / f"{stem}.stderr.log"
    previous_report_path = latest_previous_report(config.output_dir)
    previous_excerpt = read_previous_report_excerpt(previous_report_path)
    prompt = build_prompt(config.stock_pool, config.trigger, created_at, previous_excerpt)
    prompt_path.write_text(prompt, encoding="utf-8")

    meta: dict[str, Any] = {
        "run_id": config.run_id,
        "trigger": config.trigger,
        "created_at": created_at,
        "stock_pool": config.stock_pool,
        "status": "running",
        "report_path": str(report_path),
        "prompt_path": str(prompt_path),
        "stdout_log_path": str(stdout_log_path),
        "stderr_log_path": str(stderr_log_path),
        "previous_report_path": str(previous_report_path) if previous_report_path else "",
        "started_at": created_at,
        "finished_at": "",
        "error_message": "",
    }
    save_json(meta_path, meta)

    try:
        codex_path = resolve_codex_path(config.codex_path)
        check_codex_login(codex_path)
    except Exception as exc:
        write_failure_report(
            report_path,
            f"Startup failed: {exc}",
            trigger=config.trigger,
            created_at=created_at,
            stock_pool=config.stock_pool,
        )
        meta["status"] = "failed"
        meta["finished_at"] = beijing_now().strftime("%Y-%m-%d %H:%M:%S")
        meta["error_message"] = str(exc)
        save_json(meta_path, meta)
        sync_runtime_snapshot(
            config.runtime_path,
            run_id=config.run_id,
            stock_pool=config.stock_pool,
            meta=meta,
            meta_path=meta_path,
        )
        return 1

    command = [
        codex_path,
        "--search",
        "exec",
        "-s",
        "read-only",
        "--skip-git-repo-check",
        "--color",
        "never",
        "-C",
        config.workdir,
        "-o",
        str(report_path),
        "-",
    ]

    try:
        with prompt_path.open("rb") as prompt_handle:
            result = subprocess.run(
                command,
                stdin=prompt_handle,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=config.timeout_seconds,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        stdout_log_path.write_text(result.stdout or "", encoding="utf-8")
        stderr_log_path.write_text(result.stderr or "", encoding="utf-8")

        if result.returncode != 0:
            write_failure_report(
                report_path,
                f"Codex exit code: {result.returncode}\n\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}",
                trigger=config.trigger,
                created_at=created_at,
                stock_pool=config.stock_pool,
            )
            meta["status"] = "failed"
            meta["error_message"] = f"Codex exit code: {result.returncode}"
            exit_code = result.returncode or 1
        elif not report_path.exists() or not read_report_text(report_path).strip():
            write_failure_report(
                report_path,
                "Codex did not generate a valid report.",
                trigger=config.trigger,
                created_at=created_at,
                stock_pool=config.stock_pool,
            )
            meta["status"] = "failed"
            meta["error_message"] = "Codex did not generate a valid report."
            exit_code = 1
        else:
            meta["status"] = "success"
            exit_code = 0
    except subprocess.TimeoutExpired as exc:
        stdout_log_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_log_path.write_text(exc.stderr or "", encoding="utf-8")
        write_failure_report(
            report_path,
            "Codex execution timed out.",
            trigger=config.trigger,
            created_at=created_at,
            stock_pool=config.stock_pool,
        )
        meta["status"] = "timeout"
        meta["error_message"] = "Codex execution timed out."
        exit_code = 124
    except Exception as exc:  # pragma: no cover
        stderr_log_path.write_text(str(exc), encoding="utf-8")
        write_failure_report(
            report_path,
            f"Runtime error: {exc}",
            trigger=config.trigger,
            created_at=created_at,
            stock_pool=config.stock_pool,
        )
        meta["status"] = "error"
        meta["error_message"] = str(exc)
        exit_code = 1

    meta["finished_at"] = beijing_now().strftime("%Y-%m-%d %H:%M:%S")
    save_json(meta_path, meta)
    sync_runtime_snapshot(
        config.runtime_path,
        run_id=config.run_id,
        stock_pool=config.stock_pool,
        meta=meta,
        meta_path=meta_path,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

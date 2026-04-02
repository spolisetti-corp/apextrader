import os
import subprocess
import time
import sys
import atexit
from datetime import datetime, time as dtime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env before anything reads credentials — must happen before os.environ is
# copied in _mode_env() so key vars like PAPER_ALPACA_API_KEY are visible.
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(BASE_DIR / ".env", override=False)
except ImportError:
    pass  # python-dotenv not installed; rely on shell env

LOG_FILE = BASE_DIR / "autobot.log"
PID_FILE = BASE_DIR / "autobot.pid"
PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"
MAIN_SCRIPT = BASE_DIR / "main.py"
_ET = ZoneInfo("America/New_York") if ZoneInfo else None
_LIVE_WINDOWS_SPEC = os.getenv("LIVE_TRADE_WINDOWS_ET", "09:50-10:25,15:35-16:00")


def _parse_windows(spec: str):
    windows = []
    for part in (spec or "").split(","):
        p = part.strip()
        if not p or "-" not in p:
            continue
        a, b = [x.strip() for x in p.split("-", 1)]
        try:
            sh, sm = [int(x) for x in a.split(":", 1)]
            eh, em = [int(x) for x in b.split(":", 1)]
            windows.append((dtime(sh, sm), dtime(eh, em)))
        except Exception:
            continue
    return windows


_LIVE_WINDOWS = _parse_windows(_LIVE_WINDOWS_SPEC)


def _now_et() -> datetime:
    if _ET is None:
        # Safe fallback: if timezone support is unavailable, keep paper mode.
        return datetime.utcnow()
    return datetime.now(_ET)


def _is_live_window(now_et: datetime) -> bool:
    if _ET is None:
        return False
    if now_et.weekday() >= 5:  # Sat/Sun
        return False
    t = now_et.time().replace(second=0, microsecond=0)
    for start_t, end_t in _LIVE_WINDOWS:
        if start_t <= t < end_t:
            return True
    return False


def _desired_mode() -> str:
    return "live" if _is_live_window(_now_et()) else "paper"


def _mode_env(mode: str):
    env = os.environ.copy()
    env["TRADE_MODE"] = mode
    # Validate that the required credentials exist for this mode
    key_var = f"{'LIVE' if mode == 'live' else 'PAPER'}_ALPACA_API_KEY"
    if not env.get(key_var):
        raise RuntimeError(f"Missing {key_var} — set it in .env before running in {mode} mode")
    return env


def is_process_running(pid):
    """Windows-safe process existence check — only matches python.exe processes."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FI", "IMAGENAME eq python.exe", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
        return str(pid) in result.stdout
    except Exception:
        return False


def write_log(msg):
    with LOG_FILE.open("a", encoding="utf-8") as log:
        log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")


def _create_pid_file_atomic(pid: int) -> bool:
    """Create pid file atomically. Returns True only for the single winner."""
    try:
        fd = os.open(str(PID_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(str(pid))
        return True
    except FileExistsError:
        return False


def _cleanup_pid_file_if_owner(pid: int):
    try:
        if PID_FILE.exists() and PID_FILE.read_text().strip() == str(pid):
            PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


if __name__ == "__main__":
    my_pid = os.getpid()

    if not _create_pid_file_atomic(my_pid):
        existing_pid = PID_FILE.read_text(encoding="utf-8").strip() if PID_FILE.exists() else "unknown"
        write_log(f"PID lock already present (pid={existing_pid}). Exiting duplicate launcher.")
        sys.exit(0)

    atexit.register(_cleanup_pid_file_if_owner, my_pid)
    write_log("=== AutoBot watchdog started ===")
    write_log(f"PID file: {PID_FILE}")

    while True:
        try:
            launch_mode = _desired_mode()
            write_log(
                f"Launching main.py mode={launch_mode.upper()} "
                f"(windows ET: {_LIVE_WINDOWS_SPEC})"
            )
            started_at = time.time()
            saw_duplicate_main_lock = False
            proc = subprocess.Popen(
                [str(PYTHON), str(MAIN_SCRIPT)],
                cwd=str(BASE_DIR),
                env=_mode_env(launch_mode),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
            )

            last_mode_check = time.time()
            for line in proc.stdout:
                if "Another main.py instance is already running" in line:
                    saw_duplicate_main_lock = True
                write_log(line.rstrip())

                # Auto-switch between LIVE and PAPER by ET windows.
                if time.time() - last_mode_check >= 30:
                    last_mode_check = time.time()
                    now_mode = _desired_mode()
                    if now_mode != launch_mode:
                        write_log(
                            f"Mode window changed {launch_mode.upper()} -> {now_mode.upper()} "
                            "(restarting main.py)"
                        )
                        try:
                            proc.terminate()
                            proc.wait(timeout=20)
                        except Exception:
                            try:
                                proc.kill()
                            except Exception:
                                pass
                        break

            proc.wait()
            write_log(f"main.py exited with {proc.returncode}")

            # If this watchdog is the duplicate one, do not keep restarting forever.
            # Exit and let the already-running watchdog/main pair continue.
            if saw_duplicate_main_lock:
                write_log("Detected duplicate main lock; exiting duplicate watchdog.")
                break

            # Extra safety: extremely short clean exits usually indicate duplicate/lock races.
            runtime_sec = time.time() - started_at
            if proc.returncode == 0 and runtime_sec < 5:
                write_log(
                    f"main.py exited too quickly ({runtime_sec:.1f}s); "
                    "assuming duplicate/lock race and stopping watchdog."
                )
                break

        except Exception as exc:
            write_log(f"watchdog error: {exc}")

        write_log("Heartbeat: process exited, restarting in 10s")
        time.sleep(10)

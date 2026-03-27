import os
import subprocess
import time
import sys
import atexit
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "autobot.log"
PID_FILE = BASE_DIR / "autobot.pid"
PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"
MAIN_SCRIPT = BASE_DIR / "main.py"


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
            write_log("Launching main.py")
            started_at = time.time()
            saw_duplicate_main_lock = False
            proc = subprocess.Popen(
                [str(PYTHON), str(MAIN_SCRIPT)],
                cwd=str(BASE_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
            )

            for line in proc.stdout:
                if "Another main.py instance is already running" in line:
                    saw_duplicate_main_lock = True
                write_log(line.rstrip())

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

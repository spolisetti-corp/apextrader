import os
import subprocess
import time
import sys
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


if __name__ == "__main__":
    if PID_FILE.exists():
        try:
            existing_pid = int(PID_FILE.read_text().strip())
            if is_process_running(existing_pid):
                write_log(f"Existing AutoBot process is already running (pid={existing_pid}). Exiting duplicate launcher.")
                sys.exit(0)
            else:
                write_log(f"Stale PID file found (pid={existing_pid}), removing.")
                PID_FILE.unlink(missing_ok=True)
        except Exception as exc:
            write_log(f"Failed to inspect existing PID file: {exc}")

    PID_FILE.write_text(str(os.getpid()))
    write_log("=== AutoBot watchdog started ===")
    write_log(f"PID file: {PID_FILE}")

    while True:
        try:
            write_log("Launching main.py")
            proc = subprocess.Popen(
                [str(PYTHON), str(MAIN_SCRIPT)],
                cwd=str(BASE_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
            )

            for line in proc.stdout:
                write_log(line.rstrip())

            proc.wait()
            write_log(f"main.py exited with {proc.returncode}")

        except Exception as exc:
            write_log(f"watchdog error: {exc}")

        write_log("Heartbeat: process exited, restarting in 10s")
        time.sleep(10)

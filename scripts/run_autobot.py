import subprocess
import time
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "autobot.log"
PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"
MAIN_SCRIPT = BASE_DIR / "main.py"

if __name__ == "__main__":
    with LOG_FILE.open("a", encoding="utf-8") as log:
        log.write(f"\n=== AutoBot started {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")

    while True:
        try:
            with LOG_FILE.open("a", encoding="utf-8") as log:
                log.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] launching main.py...\n")

            proc = subprocess.Popen(
                [str(PYTHON), str(MAIN_SCRIPT)],
                cwd=str(BASE_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
            )

            for line in proc.stdout:
                with LOG_FILE.open("a", encoding="utf-8") as log:
                    log.write(line)

            proc.wait()
            with LOG_FILE.open("a", encoding="utf-8") as log:
                log.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] main.py exited with {proc.returncode}\n")

        except Exception as exc:
            with LOG_FILE.open("a", encoding="utf-8") as log:
                log.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] watchdog error: {exc}\n")

        time.sleep(10)

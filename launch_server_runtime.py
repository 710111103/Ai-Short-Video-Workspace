from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 5:
        return 2
    pythonw = Path(sys.argv[1]).resolve()
    out_log = Path(sys.argv[2]).resolve()
    err_log = Path(sys.argv[3]).resolve()
    pid_file = Path(sys.argv[4]).resolve()
    root = Path(__file__).resolve().parent
    out_log.parent.mkdir(parents=True, exist_ok=True)
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    creationflags = (
        subprocess.DETACHED_PROCESS
        | subprocess.CREATE_NEW_PROCESS_GROUP
        | subprocess.CREATE_NO_WINDOW
    )
    with out_log.open("wb") as stdout_handle, err_log.open("wb") as stderr_handle:
        process = subprocess.Popen(
            [str(pythonw), str(root / "run_server_runtime.py")],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=stdout_handle,
            stderr=stderr_handle,
            close_fds=True,
            creationflags=creationflags,
        )
    pid_file.write_text(str(process.pid), encoding="ascii")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Arm Linux parent-death cleanup before replacing this process with a provider CLI."""

from __future__ import annotations

import ctypes
import os
import signal
import sys


def main() -> int:
    if len(sys.argv) < 3:
        return 2
    expected_parent = int(sys.argv[1])
    command = sys.argv[2:]
    if not sys.platform.startswith("linux"):
        os.execvp(command[0], command)
    libc = ctypes.CDLL(None, use_errno=True)
    # PR_SET_PDEATHSIG sends SIGTERM to the provider process if the backend dies,
    # including SIGKILL, which Python cannot handle with a cleanup callback.
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    # Close the race where the parent exits just before prctl is armed.
    if os.getppid() != expected_parent:
        os.kill(os.getpid(), signal.SIGTERM)
        return 143
    try:
        os.execvpe(command[0], command, os.environ)
    except FileNotFoundError as exc:
        print(f"provider command is not installed: {command[0]} ({exc})", file=sys.stderr)
        return 127
    return 127


if __name__ == "__main__":
    raise SystemExit(main())

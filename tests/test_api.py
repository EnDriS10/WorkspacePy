import os
import subprocess
import sys

from workspacepy.api import _pid_alive


def test_pid_alive_own_process_and_junk():
    assert _pid_alive(os.getpid())
    assert not _pid_alive(0) and not _pid_alive(-1) and not _pid_alive(None) and not _pid_alive("abc")


def test_pid_alive_detects_dead_process_without_signalling_live_ones():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert _pid_alive(child.pid)
        assert child.poll() is None  # the check must not have killed it
    finally:
        child.kill()
        child.wait()
    assert not _pid_alive(child.pid)

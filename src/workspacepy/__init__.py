"""WorkspacePy — a MATLAB-style workspace for Jupyter / VS Code.

Minimal usage in a notebook::

    import workspacepy
    ws = workspacepy.start()      # prints short instructions; the VS Code extension opens it automatically
    ws.open()                     # or open it in your browser

or with the IPython magic::

    %load_ext workspacepy
"""

from .api import (  # noqa: F401
    Handle,
    active,
    load_ipython_extension,
    start,
    stop,
    unload_ipython_extension,
)
from .inspectors import Inspector, register  # noqa: F401
from .stats import compute_stats  # noqa: F401
from .workspace import Workspace, WorkspaceError  # noqa: F401

__version__ = "0.3.0"
__all__ = [
    "start", "stop", "active", "Handle", "Workspace", "WorkspaceError",
    "Inspector", "register", "compute_stats", "load_ipython_extension", "unload_ipython_extension",
]

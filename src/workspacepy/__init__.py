"""WorkspacePy — un workspace estilo MATLAB para Jupyter / VS Code.

Uso mínimo en un notebook::

    import workspacepy
    ws = workspacepy.start()      # imprime la URL; la extensión de VS Code lo abre al lado
    ws.open()                     # o ábrelo en el navegador

o con magia::

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

__version__ = "0.1.0"
__all__ = [
    "start", "stop", "active", "Handle", "Workspace", "WorkspaceError",
    "Inspector", "register", "compute_stats", "load_ipython_extension", "unload_ipython_extension",
]

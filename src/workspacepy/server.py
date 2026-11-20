"""Servidor HTTP local (solo 127.0.0.1) que expone un `Workspace` a la interfaz web.

Seguridad: el servidor escucha solo en loopback, exige un token aleatorio en cada petición
a /api y valida la cabecera Host (anti DNS-rebinding) y Origin. Sin dependencias externas.
"""

from __future__ import annotations

import json
import mimetypes
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from .workspace import Workspace, WorkspaceError

STATIC_DIR = Path(__file__).parent / "static"
MAX_BODY = 1_000_000


class _QuietServer(ThreadingHTTPServer):
    """Ignora desconexiones del navegador (pestaña cerrada, recarga) en vez de imprimir tracebacks."""

    def handle_error(self, request, client_address):
        import sys

        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            return
        super().handle_error(request, client_address)


class WorkspaceServer:
    """Arranca/para el servidor en un hilo demonio."""

    def __init__(self, workspace: Workspace, host: str = "127.0.0.1", port: int = 0):
        self.workspace = workspace
        self.token = secrets.token_urlsafe(16)
        self._httpd = _QuietServer((host, port), self._make_handler())
        self._httpd.daemon_threads = True
        self._thread: Optional[threading.Thread] = None

    # -------------------------------------------------------------- ciclo de vida
    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/?token={self.token}"

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> "WorkspaceServer":
        if not self.running:
            self._thread = threading.Thread(target=self._httpd.serve_forever, name="workspacepy-server", daemon=True)
            self._thread.start()
        return self

    def stop(self) -> None:
        if self.running:
            self._httpd.shutdown()
        self._httpd.server_close()

    # -------------------------------------------------------------- manejador HTTP
    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            server_version = "workspacepy"

            def log_message(self, *args):  # silencio: no ensuciar la salida del notebook
                pass

            # ---- utilidades
            def _host_ok(self) -> bool:
                host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
                if host not in ("127.0.0.1", "localhost", "::1"):
                    return False
                origin = self.headers.get("Origin")
                if origin:
                    o = urlparse(origin)
                    return (o.hostname or "").lower() in ("127.0.0.1", "localhost", "::1") and o.port == server.port
                return True

            def _token_ok(self, query) -> bool:
                supplied = self.headers.get("X-Workspace-Token") or (query.get("token") or [""])[0]
                return secrets.compare_digest(supplied, server.token)

            def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)

            def _json(self, code: int, payload):
                self._send(code, json.dumps(payload, allow_nan=False).encode("utf-8"))

            def _error(self, code: int, message: str):
                self._json(code, {"error": message})

            # ---- GET
            def do_GET(self):
                if not self._host_ok():
                    return self._error(403, "host no permitido")
                url = urlparse(self.path)
                query = parse_qs(url.query)
                if url.path.startswith("/api/"):
                    if not self._token_ok(query):
                        return self._error(401, "token inválido")
                    return self._api("GET", url.path[5:], query, {})
                return self._static(url.path, query)

            def _static(self, path: str, query):
                if path in ("/", ""):
                    path = "/index.html"
                    if not self._token_ok(query):
                        return self._send(401, "Token inválido. Abre la URL que imprime ws.open().".encode(),
                                          "text/plain; charset=utf-8")
                target = (STATIC_DIR / path.lstrip("/")).resolve()
                if STATIC_DIR.resolve() not in target.parents or not target.is_file():
                    return self._error(404, "no encontrado")
                ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                if ctype.startswith("text/") or ctype in ("application/javascript",):
                    ctype += "; charset=utf-8"
                self._send(200, target.read_bytes(), ctype)

            # ---- POST
            def do_POST(self):
                if not self._host_ok():
                    return self._error(403, "host no permitido")
                url = urlparse(self.path)
                query = parse_qs(url.query)
                if not url.path.startswith("/api/") or not self._token_ok(query):
                    return self._error(401, "token inválido")
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    return self._error(400, "Content-Length inválido")
                if length > MAX_BODY:
                    return self._error(413, "petición demasiado grande")
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    body = json.loads(raw or b"{}")
                    if not isinstance(body, dict):
                        raise ValueError
                except ValueError:
                    return self._error(400, "JSON inválido")
                return self._api("POST", url.path[5:], query, body)

            # ---- enrutado de la API
            def _api(self, method: str, route: str, query, body):
                ws = server.workspace

                def q(key, default=None):
                    return body.get(key, (query.get(key) or [default])[0])

                def path_arg():
                    p = body.get("path")
                    if p is None:
                        raw = (query.get("path") or [None])[0]
                        p = json.loads(raw) if raw else None
                    if not isinstance(p, list) or not p or not all(isinstance(s, str) for s in p):
                        raise WorkspaceError("parámetro 'path' inválido")
                    return p

                def index_arg():
                    idx = body.get("index")
                    if idx is None:
                        raw = (query.get("index") or [None])[0]
                        idx = json.loads(raw) if raw else []
                    if not isinstance(idx, list) or not all(isinstance(i, int) for i in idx):
                        raise WorkspaceError("parámetro 'index' inválido")
                    return idx

                try:
                    if method == "GET" and route == "version":
                        return self._json(200, {"version": ws.version})
                    if method == "GET" and route == "variables":
                        return self._json(200, ws.list_variables(show_hidden=str(q("hidden", "0")) == "1"))
                    if method == "GET" and route == "describe":
                        return self._json(200, ws.describe(path_arg()))
                    if method == "GET" and route == "window":
                        return self._json(200, ws.window(
                            path_arg(), q("r0", 0), q("r1", 100), q("c0", 0), q("c1", 30), index_arg(), q("digits", 6)))
                    if method == "GET" and route == "children":
                        return self._json(200, ws.children(path_arg(), q("offset", 0), q("limit", 200)))
                    if method == "GET" and route == "plot":
                        return self._json(200, ws.plot(path_arg(), str(q("kind", "line")), index_arg()))
                    if method == "POST" and route == "set_item":
                        return self._json(200, ws.set_item(path_arg(), body["row"], body["col"], body["text"], index_arg()))
                    if method == "POST" and route == "set_value":
                        return self._json(200, ws.set_value(path_arg(), body["text"]))
                    if method == "POST" and route == "delete":
                        return self._json(200, ws.delete(path_arg()[0]))
                    return self._error(404, f"ruta desconocida: {route}")
                except WorkspaceError as exc:
                    return self._error(400, str(exc))
                except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
                    return self._error(400, f"petición inválida: {exc}")
                except Exception as exc:  # no tumbar el hilo por un objeto raro
                    return self._error(500, f"{type(exc).__name__}: {exc}")

        return Handler

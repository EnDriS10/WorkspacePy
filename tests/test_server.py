import json
import urllib.error
import urllib.request

import numpy as np
import pytest

from workspacepy.server import WorkspaceServer
from workspacepy.workspace import Workspace, WorkspaceError


@pytest.fixture
def env():
    ns = {"A": np.arange(12.0).reshape(3, 4), "s": 3.5, "lst": [1, 2, 3], "_hidden": 1, "len": len}
    ws = Workspace(ns)
    srv = WorkspaceServer(ws).start()
    yield ns, ws, srv
    srv.stop()


def call(srv, path, *, token=True, data=None, host=None):
    url = f"http://127.0.0.1:{srv.port}{path}"
    if token:
        url += ("&" if "?" in url else "?") + "token=" + srv.token
    req = urllib.request.Request(url, data=None if data is None else json.dumps(data).encode(),
                                 method="POST" if data is not None else "GET")
    if host:
        req.add_header("Host", host)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_variable_listing_hides_private_and_functions(env):
    ns, ws, srv = env
    names = [v["name"] for v in call(srv, "/api/variables")[1]["variables"]]
    assert names == ["A", "lst", "s"]
    names = [v["name"] for v in call(srv, "/api/variables?hidden=1")[1]["variables"]]
    assert "len" in names and "_hidden" not in names


def test_token_and_host_are_enforced(env):
    _, _, srv = env
    assert call(srv, "/api/variables", token=False)[0] == 401
    assert call(srv, "/api/variables", host="evil.example.com")[0] == 403
    assert call(srv, "/", token=False)[0] == 401
    assert call(srv, "/api/set_item", token=False, data={})[0] == 401


def test_static_path_traversal_blocked(env):
    _, _, srv = env
    assert call(srv, "/..%2f..%2fpyproject.toml", token=False)[0] in (403, 404)
    assert call(srv, "/../server.py", token=False)[0] in (403, 404)


def test_describe_window_plot_roundtrip(env):
    _, _, srv = env
    p = "path=" + json.dumps(["A"])
    d = call(srv, "/api/describe?" + p)[1]
    assert d["stats"]["max"] == 11 and "line" in d["plots"] and d["has_table"]
    w = call(srv, "/api/window?" + p + "&r0=0&r1=2&c0=0&c1=2")[1]
    assert w["cells"] == [["0", "1"], ["4", "5"]]
    assert call(srv, "/api/plot?" + p + "&kind=hist")[1]["kind"] == "hist"
    assert call(srv, "/api/plot?" + p + "&kind=nope")[0] == 400


def test_edit_via_api_changes_kernel_and_bumps_version(env):
    ns, ws, srv = env
    v0 = ws.version
    status, body = call(srv, "/api/set_item", data={"path": ["A"], "row": 1, "col": 1, "text": "123"})
    assert status == 200 and ns["A"][1, 1] == 123 and ws.version == v0 + 1


def test_bad_requests_give_4xx_not_500(env):
    _, _, srv = env
    assert call(srv, "/api/describe?path=" + json.dumps(["nope"]))[0] == 400
    assert call(srv, "/api/describe")[0] == 400
    assert call(srv, "/api/set_item", data={"path": ["A"]})[0] == 400
    assert call(srv, "/api/unknown")[0] == 404


def test_set_value_and_delete(env):
    ns, ws, srv = env
    assert call(srv, "/api/set_value", data={"path": ["s"], "text": "[1, 2]"})[0] == 200 and ns["s"] == [1, 2]
    assert call(srv, "/api/set_value", data={"path": ["s"], "text": "__import__('os')"})[0] == 400
    assert call(srv, "/api/delete", data={"path": ["lst"]})[0] == 200 and "lst" not in ns
    assert call(srv, "/api/delete", data={"path": ["_hidden"]})[0] == 400  # variables privadas intocables


def test_nan_and_inf_produce_valid_json(env):
    ns, ws, srv = env
    ns["bad"] = np.array([np.nan, np.inf, 1.0])
    p = "path=" + json.dumps(["bad"])
    assert call(srv, "/api/describe?" + p)[0] == 200
    assert call(srv, "/api/plot?" + p + "&kind=line")[0] == 200
    assert call(srv, "/api/variables")[0] == 200


def test_workspace_error_on_missing_variable():
    with pytest.raises(WorkspaceError):
        Workspace({}).describe(["x"])

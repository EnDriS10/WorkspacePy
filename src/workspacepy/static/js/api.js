/* Cliente de la API local. Todas las rutas llevan el token que venía en la URL. */
"use strict";

const TOKEN = new URLSearchParams(location.search).get("token") || "";

const Api = {
  async call(method, route, params, body) {
    let url = "/api/" + route;
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params || {})) {
      q.set(k, typeof v === "object" ? JSON.stringify(v) : String(v));
    }
    const s = q.toString();
    if (s) url += "?" + s;
    const opts = { method, headers: { "X-Workspace-Token": TOKEN } };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    let resp;
    try {
      resp = await fetch(url, opts);
    } catch (e) {
      throw Object.assign(new Error("sin conexión con el kernel"), { offline: true });
    }
    let data = null;
    try { data = await resp.json(); } catch (e) { /* cuerpo vacío */ }
    if (!resp.ok) throw new Error((data && data.error) || ("HTTP " + resp.status));
    return data;
  },
  version() { return this.call("GET", "version"); },
  variables(hidden) { return this.call("GET", "variables", { hidden: hidden ? 1 : 0 }); },
  describe(path) { return this.call("GET", "describe", { path }); },
  window(path, r0, r1, c0, c1, index, digits) {
    return this.call("GET", "window", { path, r0, r1, c0, c1, index: index || [], digits: digits || 6 });
  },
  children(path, offset, limit) { return this.call("GET", "children", { path, offset, limit }); },
  plot(path, kind, index) { return this.call("GET", "plot", { path, kind, index: index || [] }); },
  setItem(path, row, col, text, index) { return this.call("POST", "set_item", {}, { path, row, col, text, index: index || [] }); },
  setValue(path, text) { return this.call("POST", "set_value", {}, { path, text }); },
  del(name) { return this.call("POST", "delete", {}, { path: [name] }); },
};

/* ---- utilidades de formato compartidas ---- */
const Fmt = {
  num(v) {
    if (v === null || v === undefined) return "";
    if (typeof v === "string") return v;
    if (typeof v === "boolean") return v ? "True" : "False";
    if (Number.isInteger(v) && Math.abs(v) < 1e15) return String(v);
    const a = Math.abs(v);
    if (a !== 0 && (a >= 1e6 || a < 1e-4)) return v.toExponential(4).replace(/\.?0+e/, "e");
    return String(Number(v.toPrecision(6)));
  },
  bytes(n) {
    if (n < 1024) return n + " B";
    const u = ["KB", "MB", "GB", "TB"]; let i = -1;
    do { n /= 1024; i++; } while (n >= 1024 && i < u.length - 1);
    return n.toFixed(n < 10 ? 2 : 1) + " " + u[i];
  },
};

function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== false && v !== null && v !== undefined) e.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined) e.append(kid);
  return e;
}

const pathKey = (p) => JSON.stringify(p);

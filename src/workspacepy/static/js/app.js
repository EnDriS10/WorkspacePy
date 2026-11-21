/* Application: workspace table, open-object tabs, change polling, layout and themes. */
"use strict";

const ALL_COLS = [
  ["name", "Name"], ["value", "Value"], ["size", "Size"], ["bytes", "Bytes"], ["class", "Class"],
  ["min", "Min"], ["max", "Max"], ["range", "Range"], ["mean", "Mean"], ["median", "Median"], ["mode", "Mode"],
  ["std", "Std"], ["var", "Var"], ["sum", "Sum"], ["nnz", "Nnz"], ["nans", "NaN"],
];
// Page mode: "full" (standalone: workspace + viewer), "workspace" (only the variable table) or
// "viewer" (only the object tabs). The VS Code extension shows the last two in separate panels.
const MODE = new URLSearchParams(location.search).get("mode") || "full";
const DEFAULT_COLS = ["name", "value", "size", "class"];
const STAT_COLS = new Set(["min", "max", "range", "mean", "median", "mode", "std", "var", "sum", "nnz", "nans"]);

const store = {
  get(k, d) { try { const v = localStorage.getItem("workspacepy." + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem("workspacepy." + k, JSON.stringify(v)); } catch (e) { /* no storage available */ } },
};

class App {
  constructor() {
    this.vars = [];
    this.version = -1;
    this.sort = store.get("sort", { key: "name", dir: 1 });
    this.cols = new Set(store.get("cols2", DEFAULT_COLS));
    this.selected = null;
    this.tabs = new Map();       // pathKey -> {path, viewer, tabEl, dirty}
    this.activeKey = null;
    this.hidden = false;
    this.offline = false;
    this.$ = (id) => document.getElementById(id);
    this.openSeq = 0;
    this._hostTheme = null;
    document.body.dataset.mode = MODE;
    this._initChrome();
    const solo = location.hash.startsWith("#open=");
    if (solo) document.body.classList.add("solo");
    this.refreshAll().then(() => {
      if (solo) this._openLocal(JSON.parse(decodeURIComponent(location.hash.slice(6))));
      if (MODE === "viewer") this._syncOpenRequests();
    });
    setInterval(() => this._poll(), 700);
  }

  /* ---------------------------------------------------------------- interfaz general */
  _initChrome() {
    this.$("filter").addEventListener("input", () => this.renderTable());
    this.$("btnRefresh").onclick = () => this.refreshAll();
    this.$("btnCols").append(this._colsChev = chevron(false));
    this.$("btnCols").onclick = (e) => {
      e.stopPropagation();
      if (this._colsOpen) this._closeMenus(); else this._colMenu(e.clientX, e.clientY, this.$("btnCols"));
    };
    this.$("btnLayout").onclick = () => this._setLayout(!this.$("main").classList.contains("vertical"));
    this.$("btnTheme").onclick = () => this._cycleTheme();
    this._setLayout(store.get("vertical", innerWidth < 900 || innerHeight > innerWidth));
    this._applyTheme(store.get("theme", "auto"));
    this._initSplitter();
    window.addEventListener("message", (e) => {          // theme/colors pushed by the VS Code wrapper
      if (e.source !== window.parent || !e.data) return;
      if (e.data.workspacepy === "theme") {
        this._hostTheme = e.data.theme === "dark" ? "dark" : "light";
        this._applyTheme(this._theme);
      } else if (e.data.workspacepy === "colors" && e.data.vars) {
        const root = document.documentElement.style;
        for (const [k, v] of Object.entries(e.data.vars)) if (/^--[\w-]+$/.test(k) && typeof v === "string" && v) root.setProperty(k, v);
        this._applyTheme(this._theme);               // redraw canvases with the new colors
      }
    });
    document.addEventListener("click", () => this._closeMenus());
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") this._closeMenus(); });
  }

  _closeMenus() {
    this.$("colMenu").classList.add("hidden"); this.$("ctxMenu").classList.add("hidden");
    this._colsOpen = false; setChevron(this._colsChev, false); this.$("btnCols").setAttribute("aria-expanded", "false");
  }

  _setLayout(vertical) {
    const m = this.$("main"), ws = this.$("wsPane");
    m.classList.toggle("vertical", vertical);
    this.$("splitter").setAttribute("aria-orientation", vertical ? "horizontal" : "vertical");
    ws.style.flex = "0 0 50%";
    store.set("vertical", vertical);
  }

  _applyTheme(t) {
    this._theme = t; store.set("theme", t);
    const eff = t === "auto" ? this._hostTheme : t;
    if (!eff) document.documentElement.removeAttribute("data-theme"); else document.documentElement.setAttribute("data-theme", eff);
    for (const tab of this.tabs.values()) tab.viewer.show(tab.viewer.active, true);
  }
  _cycleTheme() { this._applyTheme({ auto: "light", light: "dark", dark: "auto" }[this._theme]); }

  _initSplitter() {
    const sp = this.$("splitter"), ws = this.$("wsPane"), main = this.$("main");
    const set = (px) => { ws.style.flex = `0 0 ${Math.max(120, px)}px`; };
    sp.addEventListener("pointerdown", (e) => {
      sp.setPointerCapture(e.pointerId); sp.classList.add("drag");
      const vertical = main.classList.contains("vertical"), rect = main.getBoundingClientRect();
      const move = (ev) => set(vertical ? ev.clientY - rect.top : ev.clientX - rect.left);
      const up = () => { sp.classList.remove("drag"); sp.removeEventListener("pointermove", move); sp.removeEventListener("pointerup", up); };
      sp.addEventListener("pointermove", move); sp.addEventListener("pointerup", up);
    });
    sp.addEventListener("keydown", (e) => {
      const vertical = main.classList.contains("vertical"), cur = vertical ? ws.offsetHeight : ws.offsetWidth;
      const d = { ArrowLeft: -20, ArrowUp: -20, ArrowRight: 20, ArrowDown: 20 }[e.key];
      if (d) { e.preventDefault(); set(cur + d); }
    });
  }

  /* ---------------------------------------------------------------- sondeo y refresco */
  async _poll() {
    if (document.hidden) return;
    try {
      const { version, open_seq } = await Api.version();
      this._setOnline(true);
      if (version !== this.version) await this.refreshAll();
      if (MODE === "viewer" && open_seq !== this.openSeq) await this._syncOpenRequests();
    } catch (e) { this._setOnline(false); }
  }

  _setOnline(ok) {
    this.offline = !ok;
    const s = this.$("status");
    s.classList.toggle("off", !ok);
    s.title = ok ? "Connected" : "No connection to the kernel";
  }

  async refreshAll() {
    try {
      const r = await Api.variables(this.hidden, this._needsStats());
      this.vars = r.variables; this.version = r.version;
      this._setOnline(true);
      this.renderTable();
    } catch (e) { this._setOnline(false); return; }
    for (const tab of this.tabs.values()) tab.dirty = true;
    await this._refreshActive();
  }

  async _refreshActive() {
    const tab = this.tabs.get(this.activeKey);
    if (tab && tab.dirty) { tab.dirty = false; try { await tab.viewer.refresh(); } catch (e) { /* offline */ } }
  }

  /* ---------------------------------------------------------------- tabla del workspace */
  _cell(v, key) {
    if (STAT_COLS.has(key)) { const s = v.stats && v.stats[key]; return s === null || s === undefined ? "" : Fmt.num(s); }
    if (key === "bytes") return String(v.bytes);
    return v[key] === undefined ? "" : String(v[key]);
  }
  _sortValue(v, key) {
    if (STAT_COLS.has(key)) { const s = v.stats && v.stats[key]; return typeof s === "number" ? s : null; }
    if (key === "bytes") return v.bytes;
    return String(v[key] || "").toLowerCase();
  }

  renderTable() {
    const q = this.$("filter").value.trim().toLowerCase();
    const cols = ALL_COLS.filter(([k]) => this.cols.has(k));
    let rows = this.vars.filter((v) => !q || v.name.toLowerCase().includes(q) || v.class.toLowerCase().includes(q));
    const { key, dir } = this.sort;
    rows = rows.slice().sort((a, b) => {
      const x = this._sortValue(a, key), y = this._sortValue(b, key);
      if (x === null && y === null) return 0;
      if (x === null) return 1; if (y === null) return -1;
      return (x < y ? -1 : x > y ? 1 : 0) * dir;
    });
    const host = this.$("wsScroll"), top = host.scrollTop;
    if (!rows.length) {
      host.replaceChildren(el("div", { id: "wsEmpty", text: this.vars.length ? "No variable matches the filter." : "The workspace is empty. Create variables in your notebook." }));
      return;
    }
    const thead = el("thead", {}, el("tr", {}, cols.map(([k, label]) => {
      const th = el("th", { title: "Click: sort · right click: columns" }, label, this.sort.key === k ? el("span", { class: "arrow", text: this.sort.dir > 0 ? "▲" : "▼" }) : null);
      th.onclick = () => { this.sort = { key: k, dir: this.sort.key === k ? -this.sort.dir : 1 }; store.set("sort", this.sort); this.renderTable(); };
      th.oncontextmenu = (e) => { e.preventDefault(); e.stopPropagation(); this._colMenu(e.clientX, e.clientY); };
      return th;
    })));
    const tbody = el("tbody");
    for (const v of rows) {
      const tr = el("tr", { tabindex: "0", class: v.name === this.selected ? "sel" : "", "data-name": v.name });
      for (const [k] of cols) {
        const td = el("td", { class: (STAT_COLS.has(k) || k === "bytes" ? "num " : "") + (k === "name" ? "name" : k === "class" ? "cls" : ""), title: k === "value" ? v.value : null });
        if (k === "name") td.textContent = v.name;
        else td.textContent = this._cell(v, k);
        tr.append(td);
      }
      tr.onclick = () => { this.selected = v.name; tbody.querySelectorAll(".sel").forEach((n) => n.classList.remove("sel")); tr.classList.add("sel"); };
      tr.ondblclick = () => this.open([v.name]);
      tr.onkeydown = (e) => {
        if (e.key === "Enter") this.open([v.name]);
        else if (e.key === "Delete") this._delete(v.name);
        else if (e.key === "ArrowDown" && tr.nextSibling) { tr.nextSibling.focus(); tr.nextSibling.click(); }
        else if (e.key === "ArrowUp" && tr.previousSibling) { tr.previousSibling.focus(); tr.previousSibling.click(); }
      };
      tr.oncontextmenu = (e) => { e.preventDefault(); tr.click(); this._ctxMenu(e.clientX, e.clientY, v); };
      tbody.append(tr);
    }
    host.replaceChildren(el("table", { class: "ws" }, thead, tbody));
    host.scrollTop = top;
  }

  _menuAt(menu, x, y) {
    menu.classList.remove("hidden");
    menu.style.left = Math.min(x, innerWidth - menu.offsetWidth - 6) + "px";
    menu.style.top = Math.min(y, innerHeight - menu.offsetHeight - 6) + "px";
  }
  _colMenu(x, y, anchor) {
    const m = this.$("colMenu");
    const hid = el("input", { type: "checkbox" }); hid.checked = this.hidden;
    hid.onchange = () => { this.hidden = hid.checked; this.refreshAll(); };
    m.replaceChildren(...ALL_COLS.map(([k, label]) => {
      const cb = el("input", { type: "checkbox" }); cb.checked = this.cols.has(k); cb.disabled = k === "name";
      cb.onchange = () => { cb.checked ? this.cols.add(k) : this.cols.delete(k); store.set("cols2", [...this.cols]); this.renderTable(); };
      return el("label", { onclick: (e) => e.stopPropagation() }, cb, label);
    }), el("div", { class: "sep" }), el("label", { onclick: (e) => e.stopPropagation() }, hid, "Show functions & modules"));
    this._closeMenus();
    if (anchor) { const r = anchor.getBoundingClientRect(); x = r.left; y = r.bottom + 4; this._colsOpen = true; setChevron(this._colsChev, true); anchor.setAttribute("aria-expanded", "true"); }
    this._menuAt(m, x, y);
  }
  _ctxMenu(x, y, v) {
    this._closeMenus();
    const m = this.$("ctxMenu");
    m.replaceChildren(
      el("button", { onclick: () => this.open([v.name]) }, "Open"),
      MODE === "full" ? el("button", { onclick: () => this.popOut([v.name]) }, "Open in separate window") : null,
      el("button", { onclick: () => navigator.clipboard && navigator.clipboard.writeText(v.name).catch(() => {}) }, "Copy name"),
      el("button", { class: "danger", onclick: () => this._delete(v.name) }, "Delete variable"));
    this._menuAt(m, x, y);
  }
  async _delete(name) {
    if (!confirm(`Delete variable “${name}” from the kernel?`)) return;
    try { await Api.del(name); await this.refreshAll(); } catch (e) { alert(e.message); }
  }

  /* ---------------------------------------------------------------- object tabs */
  /* Open an object. In "workspace" mode the viewer lives in another panel/page, so ask the kernel
   * to relay the request (and tell the host, which reveals the viewer panel). */
  async open(path) {
    if (MODE !== "workspace") return this._openLocal(path);
    try { await Api.requestOpen(path); } catch (e) { alert(e.message); return; }
    try { window.parent.postMessage({ workspacepy: "open", path }, "*"); } catch (e) { /* not embedded */ }
  }

  _needsStats() { return [...this.cols].some((k) => STAT_COLS.has(k)); }

  async _syncOpenRequests() {
    let r;
    try { r = await Api.openQueue(this.openSeq); } catch (e) { return; }
    this.openSeq = r.seq;
    for (const req of r.requests) await this._openLocal(req.path);
  }

  async _openLocal(path) {
    const key = pathKey(path);
    let tab = this.tabs.get(key);
    if (!tab) {
      const viewer = new ObjectViewer(this, path);
      const label = path.length === 1 ? path[0] : path[0] + path.slice(1).map((p) => (p.startsWith("[") ? p : p.startsWith("'") ? "[" + p + "]" : "." + p)).join("");
      const tabEl = el("div", { class: "tab", role: "tab", title: path.join(" › ") },
        el("span", { text: label }),
        el("button", { class: "x", title: "Close", "aria-label": "Close tab", onclick: (e) => { e.stopPropagation(); this.close(key); } }, "×"));
      tabEl.onclick = () => this.activate(key);
      tabEl.onauxclick = (e) => { if (e.button === 1) this.close(key); };
      this.$("tabs").append(tabEl);
      this.$("viewBody").append(viewer.el);
      tab = { path, viewer, tabEl, dirty: false };
      this.tabs.set(key, tab);
      this.$("placeholder").classList.add("hidden");
      try { await viewer.load(); } catch (e) { /* offline */ }
    }
    this.activate(key);
  }

  activate(key) {
    this.activeKey = key;
    for (const [k, t] of this.tabs) {
      t.tabEl.classList.toggle("active", k === key);
      t.viewer.el.classList.toggle("active", k === key);
    }
    const tab = this.tabs.get(key);
    if (tab) { tab.tabEl.scrollIntoView({ block: "nearest", inline: "nearest" }); this._refreshActive(); }
  }

  close(key) {
    const tab = this.tabs.get(key);
    if (!tab) return;
    if (MODE === "viewer") Api.closeOpen(tab.path).catch(() => {});
    tab.tabEl.remove(); tab.viewer.el.remove(); this.tabs.delete(key);
    if (this.activeKey === key) {
      const keys = [...this.tabs.keys()];
      this.activeKey = null;
      if (keys.length) this.activate(keys[keys.length - 1]);
    }
    if (!this.tabs.size) this.$("placeholder").classList.remove("hidden");
  }

  markStale(path, stale) {
    const tab = this.tabs.get(pathKey(path));
    if (tab) tab.tabEl.classList.toggle("stale", stale);
  }

  popOut(path) {
    const url = `${location.pathname}?token=${encodeURIComponent(TOKEN)}#open=${encodeURIComponent(JSON.stringify(path))}`;
    window.open(url, "_blank", "popup,width=900,height=650");
  }
}

window.addEventListener("DOMContentLoaded", () => { window.app = new App(); });

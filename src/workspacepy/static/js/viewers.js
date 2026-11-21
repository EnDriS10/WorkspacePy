/* Object viewer: header + sub-tabs (Data / LaTeX / Contents / Plots / ...) + side panel. */
"use strict";

const STAT_LABELS = { min: "min", max: "max", range: "range", mean: "mean", median: "median", mode: "mode", std: "std", var: "var", sum: "sum", nnz: "nnz", nans: "NaN" };
const PLOT_LABELS = { line: "Line", hist: "Histogram", bar: "Bars", image: "Image" };

class ObjectViewer {
  constructor(app, path) {
    this.app = app;
    this.path = path;
    this.index = [];
    this.info = null;
    this.panes = {};      // name -> {el, dirty, ...}
    this.active = null;
    this.stale = false;
    this.el = el("div", { class: "viewer" });
    this.head = el("div", { class: "vhead" });
    this.subtabs = el("div", { class: "subtabs", role: "tablist" });
    this.paneHost = el("div", { class: "pane" });
    this.side = el("div", { class: "vside" });
    this.el.append(this.head, el("div", { class: "vbody" }, el("div", { class: "vmain" }, this.subtabs, this.paneHost), this.side));
  }

  /* ---------------------------------------------------------------- ciclo de vida */
  async load() {
    try {
      this.info = await Api.describe(this.path);
      this.stale = false;
    } catch (e) {
      if (e.offline) throw e;
      this.stale = true;
      this.paneHost.replaceChildren(el("div", { class: "errbox", text: e.message }));
      this.app.markStale(this.path, true);
      return;
    }
    this.app.markStale(this.path, false);
    this._renderHead();
    this._renderSide();
    this._renderSubtabs();
  }

  async refresh() {
    const prev = this.info && this.info.kind, prevShape = this.info && this.info.size;
    await this.load();
    if (this.stale) return;
    if (this.info.kind !== prev || this.info.size !== prevShape || !this.active || !this.names().includes(this.active)) {
      for (const p of Object.values(this.panes)) p.el.remove();
      this.panes = {};
      this.show(this.names().includes(this.active) ? this.active : this.names()[0]);
    } else {
      for (const name of Object.keys(this.panes)) this.panes[name].dirty = true;
      this.show(this.active, true);
    }
  }

  /* ---------------------------------------------------------------- cabecera y lateral */
  _renderHead() {
    const i = this.info;
    this.head.replaceChildren(
      el("span", { class: "title", text: i.title }),
      el("span", { class: "meta", text: `${i.class} · ${i.size} · ${Fmt.bytes(i.bytes)}` }),
      el("span", { class: "sp" }),
      el("button", { class: "icon popout", title: "Open in a separate window", onclick: () => this.app.popOut(this.path) }, "⧉"),
    );
  }

  _renderSide() {
    const i = this.info, nodes = [];
    nodes.push(el("h3", { text: "Properties" }));
    const kv = el("dl", { class: "kv" });
    for (const [k, v] of i.properties) kv.append(el("dt", { text: k }), el("dd", { text: v }));
    nodes.push(kv);
    const keys = Object.keys(i.stats || {}).filter((k) => i.stats[k] !== null && i.stats[k] !== undefined);
    if (keys.length) {
      nodes.push(el("h3", { text: "Statistics" }));
      const sk = el("dl", { class: "kv" });
      for (const k of keys) sk.append(el("dt", { text: STAT_LABELS[k] || k }), el("dd", { text: Fmt.num(i.stats[k]) }));
      nodes.push(sk);
      if (i.kind === "array" && i.stats.nans) nodes.push(el("div", { class: "hint", text: "min/max/mean… ignore NaNs." }));
    }
    this.side.replaceChildren(...nodes);
  }

  /* ---------------------------------------------------------------- sub-tabs */
  names() {
    const i = this.info, n = [];
    if (!i) return n;
    if (i.detail && i.detail.latex) n.push("LaTeX");
    if (i.kind === "scalar") n.push("Value");
    if (i.kind === "callable") n.push("Help");
    if (i.has_table) n.push("Data");
    if (i.n_children !== null && i.n_children !== undefined) n.push("Contents");
    if (i.detail && i.detail.columns) n.push("Columns");
    for (const p of i.plots || []) n.push(PLOT_LABELS[p] || p);
    if (!n.length) n.push("Info");
    return n;
  }

  _renderSubtabs() {
    const names = this.names();
    const tabs = names.map((n) => el("button", { class: "subtab", role: "tab", "data-name": n, onclick: () => this.show(n) }, n));
    const nodes = [...tabs];
    const lead = (this.info.detail && this.info.detail.lead_shape) || [];
    if (lead.length) {
      if (this.index.length !== lead.length) this.index = lead.map(() => 0);
      const box = el("span", { class: "slice", title: "N-d array slice: [i, j, …, :, :]" }, "slice [");
      lead.forEach((n, k) => {
        const inp = el("input", { type: "number", min: 0, max: n - 1, value: this.index[k], "aria-label": `index of dimension ${k}`,
          onchange: () => { this.index[k] = Math.max(0, Math.min(n - 1, +inp.value || 0)); inp.value = this.index[k]; this._indexChanged(); } });
        box.append(inp, k < lead.length - 1 ? ", " : "");
      });
      box.append(", :, :]");
      nodes.push(box);
    }
    this.subtabs.replaceChildren(...nodes);
    this.show(names.includes(this.active) ? this.active : names[0]);
  }

  _indexChanged() {
    for (const [name, p] of Object.entries(this.panes)) {
      p.dirty = true;
      if (p.grid) p.grid.index = this.index.slice();
    }
    this.show(this.active, true);
  }

  show(name, force) {
    this.active = name;
    for (const b of this.subtabs.querySelectorAll(".subtab")) b.classList.toggle("active", b.dataset.name === name);
    for (const p of Object.values(this.panes)) p.el.classList.add("hidden");
    let pane = this.panes[name];
    if (!pane) { pane = this.panes[name] = { dirty: true }; this._build(name, pane); }
    pane.el.classList.remove("hidden");
    if (pane.dirty || force) { pane.dirty = false; if (pane.update) pane.update(); }
  }

  _build(name, pane) {
    const i = this.info;
    let host = el("div", { class: "pane" });
    pane.el = host;
    this.paneHost.append(host);
    const plotKind = Object.keys(PLOT_LABELS).find((k) => PLOT_LABELS[k] === name);
    if (name === "Data") this._buildGrid(pane);
    else if (name === "LaTeX") this._buildLatex(pane);
    else if (name === "Value") this._buildScalar(pane);
    else if (name === "Help") this._buildHelp(pane);
    else if (name === "Contents") this._buildChildren(pane);
    else if (name === "Columns") this._buildColumns(pane);
    else if (plotKind) this._buildPlot(pane, plotKind);
    else host.append(el("div", { class: "scroll hint", text: "No additional view for this object." }));
  }

  /* ---- Datos ---- */
  _buildGrid(pane) {
    const g = new DataGrid(this.path, { editable: !!(this.info.detail && this.info.detail.editable) || this._tableEditable() });
    g.index = this.index.slice();
    pane.grid = g;
    pane.el.append(g.holder);
    g.holder.style.position = "absolute"; g.holder.style.inset = "0";
    pane.update = () => { g.index = this.index.slice(); g.editable = !!(this.info.detail && this.info.detail.editable); g.win = null; g.reload(); };
  }
  _tableEditable() { return !!(this.info.detail && this.info.detail.editable); }

  /* ---- LaTeX (SymPy) ---- */
  _buildLatex(pane) {
    const box = el("div", { class: "scroll" });
    pane.el.append(box);
    pane.update = () => {
      const d = this.info.detail, nodes = [];
      const tex = el("div", { class: "latexbox" });
      try { katex.render(d.latex, tex, { displayMode: true, throwOnError: false }); } catch (e) { tex.textContent = d.latex; }
      nodes.push(tex);
      if (d.numeric) nodes.push(el("div", { class: "bigval", text: "≈ " + d.numeric }));
      if (d.free_symbols && d.free_symbols.length) {
        nodes.push(el("div", { class: "hint", text: "Free symbols" }), el("div", { class: "chips", style: "border:0;padding:4px 0" }, d.free_symbols.map((s) => el("span", { class: "chip mono", text: s }))));
      }
      nodes.push(el("div", { class: "hint", text: "Python representation (str)" }), el("pre", { class: "code", text: d.str }));
      box.replaceChildren(...nodes);
    };
  }

  /* ---- escalares y texto ---- */
  _buildScalar(pane) {
    const box = el("div", { class: "scroll" });
    pane.el.append(box);
    pane.update = () => {
      const d = this.info.detail, isStr = this.info.class === "str";
      const raw = d.value === undefined ? "" : String(d.value);
      const lit = isStr ? "'" + raw.replace(/\\/g, "\\\\").replace(/'/g, "\\'").replace(/\n/g, "\\n") + "'" : raw;
      const input = el("input", { type: "text", class: "mono", style: "width:min(420px,100%)", value: lit, "aria-label": "new value (Python literal)" });
      const msg = el("span", { class: "hint" });
      const apply = async () => {
        try { await Api.setValue(this.path, input.value); msg.textContent = "assigned ✓"; await this.app.refreshAll(); }
        catch (e) { msg.textContent = e.message; msg.style.color = "var(--danger)"; }
      };
      input.addEventListener("keydown", (e) => { if (e.key === "Enter") apply(); });
      const nodes = [el("pre", { class: "bigval", text: raw })];
      if (d.truncated) nodes.push(el("div", { class: "hint", text: "text truncated to 20000 characters" }));
      if (d.editable) nodes.push(el("div", {}, input, " ", el("button", { onclick: apply }, "Assign"), " ", msg),
        el("div", { class: "hint", text: "Type a Python literal: 3.5, 'text', [1, 2, 3]. No code is executed." }));
      box.replaceChildren(...nodes);
    };
  }

  /* ---- functions / classes / modules ---- */
  _buildHelp(pane) {
    const box = el("div", { class: "scroll" });
    pane.el.append(box);
    pane.update = () => {
      const d = this.info.detail;
      box.replaceChildren(
        el("pre", { class: "code", text: (this.path[this.path.length - 1].replace(/^'|'$/g, "")) + (d.signature || "") }),
        el("pre", { class: "code", text: d.doc || "(no documentation)" }));
    };
  }

  /* ---- contents: lists, dicts, object attributes, DataFrame columns ---- */
  _buildChildren(pane) {
    const box = el("div", { class: "scroll" });
    pane.el.append(box);
    pane.update = async () => {
      const first = await Api.children(this.path, 0, 200);
      const table = el("table", { class: "mini" }, el("thead", {}, el("tr", {}, ["Name", "Value", "Size", "Class"].map((h) => el("th", { text: h })))));
      const body = el("tbody");
      table.append(body);
      const add = (items) => items.forEach((it) => {
        const tr = el("tr", { class: "clickable", title: "double click to open", ondblclick: () => this.app.open(this.path.concat([it.name])) },
          el("td", { class: "mono", text: it.name }), el("td", { class: "mono", text: it.value }), el("td", { text: it.size }), el("td", { class: "muted", text: it.class }));
        body.append(tr);
      });
      add(first.items);
      const more = el("button", { class: hidden(first.total, first.items.length), onclick: async () => {
        const r = await Api.children(this.path, body.children.length, 200);
        add(r.items); if (body.children.length >= first.total) more.remove();
      } }, "load more");
      box.replaceChildren(el("div", { class: "hint", text: `${first.total} items — double click to open one` }), table, more);
    };
  }

  /* ---- per-column summary (pandas) ---- */
  _buildColumns(pane) {
    const box = el("div", { class: "scroll" });
    pane.el.append(box);
    pane.update = () => {
      const cols = this.info.detail.columns;
      const num = cols.some((c) => c.min !== undefined);
      const head = ["Column", "dtype", "nulls", "unique"].concat(num ? ["min", "max", "mean", "std"] : []);
      const table = el("table", { class: "mini" }, el("thead", {}, el("tr", {}, head.map((h) => el("th", { text: h })))));
      const body = el("tbody");
      for (const c of cols) {
        const cells = [c.name, c.dtype, c.nulls, c.nunique === null ? "—" : c.nunique];
        if (num) for (const k of ["min", "max", "mean", "std"]) cells.push(c[k] === undefined || c[k] === null ? "" : Fmt.num(c[k]));
        body.append(el("tr", { class: "clickable", ondblclick: () => this.app.open(this.path.concat([c.name])) },
          cells.map((t, j) => el("td", { class: j > 1 ? "r" : "mono", text: String(t) }))));
      }
      table.append(body);
      box.replaceChildren(table, this.info.detail.columns_truncated ? el("div", { class: "hint", text: "showing the first 100 columns" }) : "");
    };
  }

  /* ---- plots ---- */
  _buildPlot(pane, kind) {
    const canvas = el("canvas");
    const box = el("div", { class: "plotbox" }, canvas);
    const note = el("div", { class: "hint", style: "position:absolute;left:12px;top:6px" });
    pane.el.append(box, note);
    let last = null;
    const redraw = () => { if (last && pane.el.offsetParent) Plots.draw(canvas, last); };
    new ResizeObserver(redraw).observe(box);
    pane.update = async () => {
      try { last = await Api.plot(this.path, kind, this.index); note.textContent = ""; redraw(); }
      catch (e) { last = null; note.textContent = e.message; }
    };
  }
}

function hidden(total, shown) { return total > shown ? "" : "hidden"; }

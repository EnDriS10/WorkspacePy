/* Virtualized, editable data grid (spreadsheet style / MATLAB Variable Editor).
 * It only asks the kernel for the visible window; it handles billions of cells because it never renders them. */
"use strict";

class DataGrid {
  constructor(path, { editable = false, onNote = () => {}, digits = 6 } = {}) {
    this.path = path;
    this.editable = editable;
    this.onNote = onNote;
    this.digits = digits;
    this.index = [];
    this.ROWH = 24;
    this.colW = 96;
    this.rowHeadW = 48;
    this.nrows = 0; this.ncols = 0;
    this.win = null;
    this.cur = { r: 0, c: 0 };
    this._seq = 0;
    this._raf = 0;
    this._build();
  }

  _build() {
    this.el = el("div", { class: "gridwrap", tabindex: "0" });
    this.sizer = el("div", { class: "g-sizer" });
    this.corner = el("div", { class: "g-corner" });
    this.colhead = el("div", { class: "g-colhead" });
    this.rowhead = el("div", { class: "g-rowhead" });
    this.cells = el("div", { class: "g-cells" });
    this.note = el("div", { class: "gridnote hidden" });
    this.sizer.append(this.corner, this.colhead, this.rowhead, this.cells);
    this.el.append(this.sizer);
    this.holder = el("div", { class: "pane" }, this.el, this.note);
    this.el.addEventListener("scroll", () => this._schedule());
    this.el.addEventListener("keydown", (e) => this._key(e));
    this.cells.addEventListener("mousedown", (e) => this._click(e));
    this.cells.addEventListener("dblclick", (e) => { const t = this._cellOf(e); if (t) { this.cur = t; this._edit(); } });
    new ResizeObserver(() => this._schedule()).observe(this.el);
  }

  /* ---------------------------------------------------------------- loading */
  setIndex(idx) { this.index = idx.slice(); this.win = null; this.reload(); }

  async reload() { await this._fetch(true); }

  _schedule() {
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => { this._raf = 0; this._fetch(false); });
  }

  _wanted() {
    const vw = this.el.clientWidth, vh = this.el.clientHeight, B = 6;
    const r0 = Math.max(0, Math.floor(this.el.scrollTop / this.ROWH) - B);
    const c0 = Math.max(0, Math.floor(this.el.scrollLeft / this.colW) - 2);
    const r1 = Math.min(this.nrows || 1e12, r0 + Math.ceil(vh / this.ROWH) + 2 * B);
    const c1 = Math.min(this.ncols || 1e12, c0 + Math.ceil(vw / this.colW) + 4);
    return { r0, r1, c0, c1 };
  }

  async _fetch(force) {
    const w = this._wanted(), cur = this.win;
    if (!force && cur && w.r0 >= cur.r0 && w.r1 <= cur.r1 && w.c0 >= cur.c0 && w.c1 <= cur.c1) { this._render(); return; }
    const seq = ++this._seq;
    // pad the requested window a little to avoid refetching on every row
    const r0 = Math.max(0, w.r0 - 20), c0 = Math.max(0, w.c0 - 4);
    try {
      const win = await Api.window(this.path, r0, Math.max(w.r1 + 20, r0 + 1), c0, Math.max(w.c1 + 6, c0 + 1), this.index, this.digits);
      if (seq !== this._seq) return;
      this.win = win;
      this.nrows = win.nrows; this.ncols = win.ncols;
      this._autoWidth();
      this._render();
      this._flash(null);
    } catch (e) {
      if (seq === this._seq) this._flash(e.message, true);
    }
  }

  _autoWidth() {
    let m = 0;
    for (const row of this.win.cells) for (const t of row) if (t.length > m) m = t.length;
    for (const t of this.win.col_labels) if (t.length > m) m = t.length;
    this.colW = Math.max(this.colW, Math.min(240, Math.round(m * 7.4 + 18)));
    let lm = String(this.nrows).length;
    for (const t of this.win.row_labels) if (t.length > lm) lm = t.length;
    this.rowHeadW = Math.max(44, Math.min(160, lm * 8 + 18));
  }

  /* ---------------------------------------------------------------- drawing */
  _render() {
    const w = this.win;
    if (!w) return;
    const H = this.ROWH;
    this.sizer.style.width = this.rowHeadW + w.ncols * this.colW + "px";
    this.sizer.style.height = H + w.nrows * H + "px";
    this.corner.style.width = this.rowHeadW + "px";
    this.colhead.style.height = H + "px";
    this.rowhead.style.width = this.rowHeadW + "px";
    this.rowhead.style.height = w.nrows * H + "px";
    this.cells.style.left = this.rowHeadW + "px";
    this.cells.style.top = H + "px";

    const ch = [], rh = [], cl = [];
    for (let j = 0; j < w.c1 - w.c0; j++) {
      ch.push(`<div class="g-ch" style="left:${this.rowHeadW + (w.c0 + j) * this.colW}px;width:${this.colW}px">${esc(w.col_labels[j])}</div>`);
    }
    for (let i = 0; i < w.r1 - w.r0; i++) {
      rh.push(`<div class="g-rh" style="top:${(w.r0 + i) * H}px">${esc(w.row_labels[i])}</div>`);
      const row = w.cells[i];
      for (let j = 0; j < row.length; j++) {
        const r = w.r0 + i, c = w.c0 + j, t = row[j];
        const isCur = r === this.cur.r && c === this.cur.c;
        cl.push(`<div class="g-c${NUMLIKE.test(t) ? "" : " text"}${isCur ? " cur" : ""}" data-r="${r}" data-c="${c}" style="left:${c * this.colW}px;top:${r * H}px;width:${this.colW}px" title="${esc(t)}">${esc(t)}</div>`);
      }
    }
    this.colhead.innerHTML = ch.join("");
    this.rowhead.innerHTML = rh.join("");
    this.cells.innerHTML = cl.join("");
  }

  /* ---------------------------------------------------------------- interaction */
  _cellOf(e) {
    const t = e.target.closest(".g-c");
    return t ? { r: +t.dataset.r, c: +t.dataset.c } : null;
  }
  _click(e) {
    const t = this._cellOf(e);
    if (!t) return;
    this._finishEdit(false);
    this.cur = t; this._markCur(); this.el.focus({ preventScroll: true });
  }
  _markCur() {
    this.cells.querySelectorAll(".cur").forEach((n) => n.classList.remove("cur"));
    const n = this.cells.querySelector(`[data-r="${this.cur.r}"][data-c="${this.cur.c}"]`);
    if (n) n.classList.add("cur");
  }
  _move(dr, dc) {
    this.cur = { r: Math.max(0, Math.min(this.nrows - 1, this.cur.r + dr)), c: Math.max(0, Math.min(this.ncols - 1, this.cur.c + dc)) };
    // mantener visible
    const H = this.ROWH, top = this.cur.r * H, left = this.cur.c * this.colW;
    const vh = this.el.clientHeight - H, vw = this.el.clientWidth - this.rowHeadW;
    if (top < this.el.scrollTop) this.el.scrollTop = top;
    else if (top + H > this.el.scrollTop + vh) this.el.scrollTop = top + H - vh;
    if (left < this.el.scrollLeft) this.el.scrollLeft = left;
    else if (left + this.colW > this.el.scrollLeft + vw) this.el.scrollLeft = left + this.colW - vw;
    this._markCur(); this._schedule();
  }
  _key(e) {
    if (this.input) return;
    const k = e.key, page = Math.max(1, Math.floor(this.el.clientHeight / this.ROWH) - 2);
    const map = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1], PageUp: [-page, 0], PageDown: [page, 0], Home: [0, -1e9], End: [0, 1e9] };
    if (map[k]) { e.preventDefault(); this._move(...map[k]); return; }
    if (k === "Enter" || k === "F2") { e.preventDefault(); this._edit(); return; }
    if ((e.ctrlKey || e.metaKey) && k.toLowerCase() === "c") { const t = this._cellText(this.cur.r, this.cur.c); if (t !== null && navigator.clipboard) navigator.clipboard.writeText(t).catch(() => {}); return; }
    if (this.editable && k.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); this._edit(k); }
  }
  _cellText(r, c) {
    const w = this.win;
    if (!w || r < w.r0 || r >= w.r1 || c < w.c0 || c >= w.c1) return null;
    return w.cells[r - w.r0][c - w.c0];
  }

  /* ---------------------------------------------------------------- editing */
  _edit(initial) {
    if (!this.editable) { this._flash("this object is read-only", true); return; }
    const text = this._cellText(this.cur.r, this.cur.c);
    if (text === null) return;
    const node = this.cells.querySelector(`[data-r="${this.cur.r}"][data-c="${this.cur.c}"]`);
    if (!node) return;
    const input = el("input", { type: "text", class: "g-input", value: initial !== undefined ? initial : text, "aria-label": "cell value" });
    node.textContent = ""; node.classList.add("editing"); node.append(input);
    this.input = input; input.focus();
    if (initial === undefined) input.select(); else input.setSelectionRange(input.value.length, input.value.length);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); this._finishEdit(true, [1, 0]); }
      else if (e.key === "Tab") { e.preventDefault(); e.stopPropagation(); this._finishEdit(true, [0, e.shiftKey ? -1 : 1]); }
      else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); this._finishEdit(false); }
      else e.stopPropagation();
    });
    input.addEventListener("blur", () => { if (this.input === input) this._finishEdit(false); });
  }

  async _finishEdit(commit, step) {
    const input = this.input;
    if (!input) return;
    this.input = null;
    const text = input.value, { r, c } = this.cur;
    if (commit) {
      try {
        await Api.setItem(this.path, r, c, text, this.index);
        await this.reload();
        this._flash(null);
      } catch (e) { this._flash(e.message, true); await this.reload(); }
    } else { this._render(); }
    this.el.focus({ preventScroll: true });
    if (commit && step) this._move(step[0], step[1]);
  }

  _flash(msg, isErr) {
    this.note.classList.toggle("hidden", !msg);
    this.note.classList.toggle("err", !!isErr);
    this.note.textContent = msg || "";
    if (msg) { clearTimeout(this._nt); this._nt = setTimeout(() => this.note.classList.add("hidden"), 5000); }
  }
}

const NUMLIKE = /^[-+]?(\d|\.\d|NaN|Inf|True$|False$)/;
function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

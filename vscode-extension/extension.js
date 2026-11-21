// WorkspacePy for VS Code.
//
// Two webviews, MATLAB style:
//   * "Workspace"       (side bar view) - the variable table. Drag it anywhere (Secondary Side Bar, bottom panel...).
//   * "Variable Viewer" (editor tab)    - opens to the RIGHT of your code when you double-click a variable.
//                                         It is a normal editor tab, so you can drag it to any editor group,
//                                         split it, or float it into its own window.
// Both are thin wrappers around iframes served by the kernel (workspacepy.start()), so they see and
// edit the variables of the running notebook. The extension only reads ~/.workspacepy/active.json.
"use strict";
const vscode = require("vscode");
const fs = require("fs");
const os = require("os");
const path = require("path");
const http = require("http");
const crypto = require("crypto");

const WORKSPACE_VIEW = "workspacepy.workspace";
const VIEWER_TYPE = "workspacepy.viewer";

function registryFile() {
  const custom = vscode.workspace.getConfiguration("workspacepy").get("registryPath");
  if (custom) return custom;
  const home = process.env.WORKSPACEPY_HOME || path.join(os.homedir(), ".workspacepy");
  return path.join(home, "active.json");
}

function alive(pid) {
  try { process.kill(pid, 0); return true; } catch (e) { return e.code === "EPERM"; }
}

function readEntries() {
  try {
    const data = JSON.parse(fs.readFileSync(registryFile(), "utf8"));
    return Object.entries(data)
      .map(([port, v]) => ({ port, url: v.url, pid: v.pid, time: v.time || 0 }))
      .filter((e) => typeof e.url === "string" && /^http:\/\/(127\.0\.0\.1|localhost):\d+\//.test(e.url) && alive(e.pid))
      .sort((a, b) => b.time - a.time);
  } catch (e) {
    return [];
  }
}

// ----------------------------------------------------------------------------- HTML of the wrappers
function wrapperHtml(src, bgVar = "--vscode-editor-background") {
  const nonce = crypto.randomBytes(16).toString("hex");
  return `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; frame-src http://localhost:* http://127.0.0.1:* https:; script-src 'nonce-${nonce}'; style-src 'unsafe-inline';">
<style>html,body{margin:0;padding:0;height:100%;overflow:hidden;background:transparent}
iframe{position:fixed;inset:0;width:100%;height:100%;border:0;color-scheme:normal}
body{background:var(${bgVar})}</style></head>
<body>
<iframe id="f" src="${src}" title="WorkspacePy"></iframe>
<script nonce="${nonce}">
  const vscode = acquireVsCodeApi();
  const f = document.getElementById("f");
  const theme = () => (document.body.classList.contains("vscode-light") || document.body.classList.contains("vscode-high-contrast-light")) ? "light" : "dark";
  const BG = ${JSON.stringify(bgVar)};
  const MAP = { "--bg": BG, "--text": "--vscode-foreground", "--muted": "--vscode-descriptionForeground",
    "--border": "--vscode-widget-border", "--accent": "--vscode-textLink-foreground", "--panel-2": "--vscode-input-background",
    "--font": "--vscode-font-family", "--mono": "--vscode-editor-font-family" };
  const sendTheme = () => {
    if (!f.contentWindow) return;
    const cs = getComputedStyle(document.documentElement), vars = {};
    for (const [k, src] of Object.entries(MAP)) { const v = cs.getPropertyValue(src).trim(); if (v) vars[k] = v; }
    if (!vars["--border"]) { const p = cs.getPropertyValue("--vscode-panel-border").trim(); if (p) vars["--border"] = p; }
    f.contentWindow.postMessage({ workspacepy: "theme", theme: theme() }, "*");
    f.contentWindow.postMessage({ workspacepy: "colors", vars }, "*");
  };
  f.addEventListener("load", sendTheme);
  new MutationObserver(sendTheme).observe(document.body, { attributes: true, attributeFilter: ["class", "style"] });
  new MutationObserver(sendTheme).observe(document.documentElement, { attributes: true, attributeFilter: ["style"] });
  window.addEventListener("message", (e) => {
    if (e.source === f.contentWindow) {                       // from the page inside the iframe
      if (e.data && e.data.workspacepy === "open") vscode.postMessage({ type: "open", path: e.data.path });
    }
  });
</script></body></html>`;
}

function placeholderHtml(text) {
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline';">
<style>body{font:13px var(--vscode-font-family);color:var(--vscode-foreground);padding:14px;line-height:1.5}
code{font-family:var(--vscode-editor-font-family);background:var(--vscode-textCodeBlock-background);padding:1px 5px;border-radius:4px}</style></head>
<body>${text}</body></html>`;
}

const NO_KERNEL = placeholderHtml(
  `<b>No active workspace.</b><br>Run this in a notebook cell:<br><br>` +
  `<code>import workspacepy</code><br><code>workspacepy.start()</code><br><br>` +
  `This panel connects by itself.`);

// ----------------------------------------------------------------------------- views
// Build the iframe URL for a panel (token kept intact, port mapped for remote windows).
async function buildSrc(entry, mode, webview) {
  const u = new URL(entry.url);
  const port = Number(u.port);
  u.hostname = "localhost";                       // lets VS Code map/forward the port (also in remote windows)
  u.searchParams.set("mode", mode);
  webview.options = { enableScripts: true, portMapping: [{ webviewPort: port, extensionHostPort: port }] };
  let src = u.toString();
  try {
    // toString(true) = skip encoding: the default encoding turns "?token=x&mode=y" into "?token%3Dx%26mode%3Dy",
    // and the server would then reject the request with "Invalid token".
    const ext = (await vscode.env.asExternalUri(vscode.Uri.parse(src))).toString(true);
    if (/[?&]token=/.test(ext)) src = ext;     // never use a URL that lost its token
  } catch (e) { /* keep the local URL */ }
  return src.replace(/"/g, "&quot;");
}

// The Variable Viewer: an editor-area tab that opens beside the code.
class ViewerPanel {
  constructor(controller) { this.controller = controller; this.panel = undefined; }

  attach(panel) {
    this.panel = panel;
    panel.iconPath = vscode.Uri.file(path.join(__dirname, "media", "icon.svg"));
    panel.onDidDispose(() => { if (this.panel === panel) this.panel = undefined; });
    panel.webview.onDidReceiveMessage((m) => this.controller.onMessage("viewer", m));
    this.render();
  }

  // Show the viewer. First time: to the right of the active editor, without stealing focus.
  // Later: reveal it where the user left it (so a dragged tab stays where it was dropped).
  show() {
    if (this.panel) { this.panel.reveal(undefined, true); return; }
    const panel = vscode.window.createWebviewPanel(VIEWER_TYPE, "Variable Viewer",
      { viewColumn: vscode.ViewColumn.Beside, preserveFocus: true },
      { enableScripts: true, retainContextWhenHidden: true });
    this.attach(panel);
  }

  async render() {
    if (!this.panel) return;
    const entry = this.controller.entry;
    if (!entry) { this.panel.webview.html = NO_KERNEL; return; }
    const src = await buildSrc(entry, "viewer", this.panel.webview);
    if (this.panel) this.panel.webview.html = wrapperHtml(src, "--vscode-editor-background");
  }
}

class PanelProvider {
  constructor(mode, controller) { this.mode = mode; this.controller = controller; this.view = undefined; }

  resolveWebviewView(view) {
    this.view = view;
    view.webview.options = { enableScripts: true };
    view.onDidDispose(() => { if (this.view === view) this.view = undefined; });
    view.webview.onDidReceiveMessage((m) => this.controller.onMessage(this.mode, m));
    this.render();
  }

  async render() {
    if (!this.view) return;
    const entry = this.controller.entry;
    if (!entry) { this.view.webview.html = NO_KERNEL; return; }
    const src = await buildSrc(entry, this.mode, this.view.webview);
    if (this.view) this.view.webview.html = wrapperHtml(src, "--vscode-sideBar-background");
  }
}

class Controller {
  constructor() {
    this.entry = undefined;
    this.pinned = undefined;
    this.seen = new Set();
    this.warned = new Set();
    this.workspace = new PanelProvider("workspace", this);
    this.viewer = new ViewerPanel(this);
  }

  // Pick the newest live kernel (or the pinned one) and refresh the wrappers if it changed.
  refresh(force) {
    const entries = readEntries();
    const next = (this.pinned && alive(this.pinned.pid) ? this.pinned : undefined) || entries[0];
    const changed = (next && next.url) !== (this.entry && this.entry.url);
    this.entry = next;
    if (changed || force) { this.workspace.render(); this.viewer.render(); }
    if (next && changed) this.checkVersion(next);
    // Reveal the Workspace view for kernels that just started.
    if (next && !this.seen.has(next.port) && Date.now() / 1000 - next.time < 120) {
      this.seen.add(next.port);
      if (vscode.workspace.getConfiguration("workspacepy").get("autoReveal")) this.revealWorkspace();
    }
  }

  async revealWorkspace() {
    if (this.workspace.view) this.workspace.view.show(true);
    else await vscode.commands.executeCommand(WORKSPACE_VIEW + ".focus");
  }

  revealViewer() { this.viewer.show(); }

  onMessage(mode, m) {
    if (mode === "workspace" && m && m.type === "open") this.revealViewer();
  }

  // Warn when the Python library and the extension are from different releases.
  checkVersion(entry) {
    const mine = vscode.extensions.getExtension("workspacepy.workspacepy");
    const extVersion = mine ? mine.packageJSON.version : null;
    const u = new URL(entry.url);
    const req = http.get({ host: u.hostname, port: u.port, path: "/api/info", timeout: 2000, headers: { "X-Workspace-Token": u.searchParams.get("token") || "" } }, (res) => {
      let body = "";
      res.on("data", (c) => (body += c));
      res.on("end", () => {
        try {
          const lib = JSON.parse(body).version;
          const mm = (v) => String(v).split(".").slice(0, 2).join(".");
          if (extVersion && mm(lib) !== mm(extVersion) && !this.warned.has(lib)) {
            this.warned.add(lib);
            vscode.window.showWarningMessage(
              `WorkspacePy: the Python library is ${lib} but the extension is ${extVersion}. ` +
              `Update the one that is older (pip install -U ... / install the new .vsix), then restart the kernel and reload the window.`);
          }
        } catch (e) { /* ignore */ }
      });
    });
    req.on("error", () => {});
    req.on("timeout", () => req.destroy());
  }
}

const LAYOUT_HELP =
  "MATLAB layout: 1) Click the WorkspacePy icon in the Activity Bar. " +
  "2) Drag the 'Workspace' view to the right edge of the window (it creates the Secondary Side Bar). " +
  "The 'Variable Viewer' opens by itself to the right of your code when you double-click a variable; " +
  "it is a normal editor tab, so drag it to any other editor group or split it. " +
  "You can also drag the 'Workspace' view to the bottom panel or the left side bar.";

function activate(context) {
  const c = new Controller();
  const opts = { webviewOptions: { retainContextWhenHidden: true } };
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(WORKSPACE_VIEW, c.workspace, opts),
    vscode.window.registerWebviewPanelSerializer(VIEWER_TYPE, {
      async deserializeWebviewPanel(panel) { panel.webview.options = { enableScripts: true }; c.viewer.attach(panel); },
    }),
    vscode.commands.registerCommand("workspacepy.openViewer", () => c.revealViewer()),
    vscode.commands.registerCommand("workspacepy.open", () => c.revealWorkspace()),
    vscode.commands.registerCommand("workspacepy.reconnect", () => { c.pinned = undefined; c.refresh(true); }),
    vscode.commands.registerCommand("workspacepy.layoutHelp", async () => {
      const pick = await vscode.window.showInformationMessage(LAYOUT_HELP, "Open 'Move View' picker");
      if (pick) { try { await vscode.commands.executeCommand("workbench.action.moveView"); } catch (e) { /* older VS Code */ } }
    }),
    vscode.commands.registerCommand("workspacepy.openUrl", async () => {
      const url = await vscode.window.showInputBox({ prompt: "URL printed by workspacepy.start()", placeHolder: "http://127.0.0.1:PORT/?token=…" });
      if (!url) return;
      if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+\//.test(url)) { vscode.window.showWarningMessage("The URL must be local (http://127.0.0.1:PORT/…)."); return; }
      c.pinned = { url, port: new URL(url).port, pid: process.pid, time: Date.now() / 1000 };
      c.refresh(true);
    })
  );

  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 0);
  status.text = "$(table) WorkspacePy";
  status.tooltip = "Show the WorkspacePy workspace";
  status.command = "workspacepy.open";
  status.show();
  context.subscriptions.push(status);

  // Watch the registry (the file is replaced atomically, so watch the directory) + a polling safety net.
  const dir = path.dirname(registryFile());
  let timer;
  const check = () => { clearTimeout(timer); timer = setTimeout(() => c.refresh(false), 300); };
  try {
    fs.mkdirSync(dir, { recursive: true });
    const w = fs.watch(dir, check);
    context.subscriptions.push({ dispose: () => w.close() });
  } catch (e) { /* no watcher: polling still works */ }
  const poll = setInterval(() => c.refresh(false), 4000);
  context.subscriptions.push({ dispose: () => clearInterval(poll) });
  c.refresh(true);
}

function deactivate() {}
module.exports = { activate, deactivate };

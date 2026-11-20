// Extensión mínima: lee el registro que escribe workspacepy.start() y abre la interfaz
// en el Simple Browser de VS Code, en una columna al lado de tu notebook.
"use strict";
const vscode = require("vscode");
const fs = require("fs");
const os = require("os");
const path = require("path");

const opened = new Set(); // puertos ya abiertos automáticamente en esta sesión
let statusItem;

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
      .filter((e) => typeof e.url === "string" && e.url.startsWith("http://127.0.0.1:") && alive(e.pid))
      .sort((a, b) => b.time - a.time);
  } catch (e) {
    return [];
  }
}

async function openUrl(url) {
  await vscode.commands.executeCommand("simpleBrowser.api.open", url, {
    viewColumn: vscode.ViewColumn.Beside,
    preserveFocus: true,
  });
}

async function openCommand() {
  const entries = readEntries();
  if (!entries.length) {
    vscode.window.showInformationMessage(
      "No hay ningún workspace activo. Ejecuta en tu notebook:  import workspacepy; workspacepy.start()"
    );
    return;
  }
  let pick = entries[0];
  if (entries.length > 1) {
    const sel = await vscode.window.showQuickPick(
      entries.map((e) => ({ label: `Kernel pid ${e.pid}`, description: `puerto ${e.port}`, e })),
      { placeHolder: "Varios kernels con WorkspacePy activo: elige uno" }
    );
    if (!sel) return;
    pick = sel.e;
  }
  opened.add(pick.port);
  await openUrl(pick.url);
}

async function openUrlCommand() {
  const url = await vscode.window.showInputBox({ prompt: "URL que imprime workspacepy.start()", placeHolder: "http://127.0.0.1:PUERTO/?token=…" });
  if (url && /^http:\/\/(127\.0\.0\.1|localhost):\d+\//.test(url)) await openUrl(url);
  else if (url) vscode.window.showWarningMessage("La URL debe ser local (http://127.0.0.1:PUERTO/…).");
}

function autoOpenNew() {
  if (!vscode.workspace.getConfiguration("workspacepy").get("autoOpen")) return;
  for (const e of readEntries()) {
    if (!opened.has(e.port) && Date.now() / 1000 - e.time < 120) { // solo servidores recién creados
      opened.add(e.port);
      openUrl(e.url);
    }
  }
}

function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand("workspacepy.open", openCommand),
    vscode.commands.registerCommand("workspacepy.openUrl", openUrlCommand)
  );
  statusItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 0);
  statusItem.text = "$(table) WorkspacePy";
  statusItem.tooltip = "Abrir el workspace al lado";
  statusItem.command = "workspacepy.open";
  statusItem.show();
  context.subscriptions.push(statusItem);

  // Vigilar el registro: fs.watch sobre el directorio (el archivo se reemplaza atómicamente).
  const dir = path.dirname(registryFile());
  let timer;
  const check = () => { clearTimeout(timer); timer = setTimeout(autoOpenNew, 300); };
  try {
    fs.mkdirSync(dir, { recursive: true });
    const w = fs.watch(dir, check);
    context.subscriptions.push({ dispose: () => w.close() });
  } catch (e) { /* sin watch: queda el comando manual */ }
  const poll = setInterval(autoOpenNew, 5000); // red de seguridad (fs.watch no es fiable en red/WSL)
  context.subscriptions.push({ dispose: () => clearInterval(poll) });
}

function deactivate() {}
module.exports = { activate, deactivate };

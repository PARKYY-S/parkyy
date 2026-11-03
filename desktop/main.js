// PARKYY desktop layer for Windows.
// - A see-through, frameless layer over your whole desktop (no taskbar icon)
// - Starts with Windows
// - Ctrl+Space summons PARKYY; tray icon (bottom-right) to show / lock / quit
// - Starts LM Studio's server + Hermes and PARKYY's backend if they aren't running
const { app, BrowserWindow, Tray, Menu, globalShortcut, ipcMain, screen, nativeImage } = require('electron');
const path = require('path');
const fs = require('fs');
const os = require('os');
const http = require('http');
const { spawn } = require('child_process');

const ROOT = path.resolve(__dirname, '..');           // the parkyy folder (main.py, agent.py …)
const LOG = path.join(ROOT, 'desktop', 'parkyy-desktop.log');
// the log is capped: past ~20 MB it is renamed to parkyy-desktop.log.old (replacing the previous .old)
let logN = 0;
function log(...a) {
  try {
    if ((logN++ % 500) === 0 && fs.existsSync(LOG) && fs.statSync(LOG).size > 20e6) fs.renameSync(LOG, LOG + '.old');
    fs.appendFileSync(LOG, new Date().toISOString() + ' ' + a.join(' ') + '\n');
  } catch (_) {}
}

// PARKYY roams the whole desktop (walks along your windows, flies) - see pet-main.js / roam.js / roam.html. Off with PARKYY_PET=0.
const roam = require('./pet-main')({ log, getWin: () => win, summon: () => summon() });

function readToken() {
  try {
    const env = fs.readFileSync(path.join(ROOT, '.env'), 'utf8');
    const m = env.match(/^\s*PARKYY_AUTH_TOKEN\s*=\s*(.+)\s*$/m);
    if (m) return m[1].trim().replace(/^["']|["']$/g, '');
  } catch (_) {}
  return 'parkyy-local';
}
const TOKEN = readToken();

function ping(url) {
  return new Promise(res => {
    const r = http.get(url, x => { x.resume(); res(x.statusCode === 200); });
    r.on('error', () => res(false)); r.setTimeout(1500, () => { r.destroy(); res(false); });
  });
}

let backend = null;
async function startServices() {
  // 1) LM Studio server + Hermes (uses LM Studio's own "lms" command)
  const lms = path.join(os.homedir(), '.lmstudio', 'bin', 'lms.exe');
  // The offline brain uses several GB of memory, so only load it at start-up when PARKYY is set to the
  // local brain. Otherwise the backend loads it by itself only when it's needed (no internet / cloud down).
  let brainMode = 'auto';
  try { brainMode = JSON.parse(fs.readFileSync(path.join(ROOT, 'brains.json'), 'utf8')).mode || 'auto'; } catch (e) {}
  if (brainMode === 'local' && !(await ping('http://127.0.0.1:1234/v1/models'))) {
    if (fs.existsSync(lms)) {
      log('starting LM Studio server');
      const s = spawn(lms, ['server', 'start'], { windowsHide: true });
      s.on('exit', () => {
        // which brain? brain.json is written when PARKYY upgrades itself
        let model = 'hermes-2-pro-llama-3-8b';
        try { model = JSON.parse(fs.readFileSync(path.join(ROOT, 'brain.json'), 'utf8')).model || model; } catch (e) {}
        log('loading brain', model);
        spawn(lms, ['load', model, '-y'], { windowsHide: true })
          .on('exit', c => log('lms load exit', c));
      });
    } else log('lms.exe not found - open LM Studio and start the server manually');
  }
  // 2) PARKYY backend (FastAPI) on this laptop only
  if (!(await ping('http://127.0.0.1:8000/health'))) {
    const py = path.join(ROOT, 'venv', 'Scripts', 'python.exe');
    if (fs.existsSync(py)) {
      log('starting backend');
      // 127.0.0.1 = laptop only. Set PARKYY_LAN=1 so the phone app can reach PARKYY over your Wi-Fi.
      const host = process.env.PARKYY_LAN === '1' ? '0.0.0.0' : '127.0.0.1';
      backend = spawn(py, ['-m', 'uvicorn', 'main:app', '--host', host, '--port', '8000'],
        { cwd: ROOT, windowsHide: true });
      backend.stdout.on('data', d => log('[api]', String(d).trim()));
      backend.stderr.on('data', d => log('[api]', String(d).trim()));
      backend.on('exit', c => log('backend exited', c));
      // 3) PARKYY's ears: "Hey PARKYY" voice input (free, offline). Off with PARKYY_VOICE_INPUT=0
      if (process.env.PARKYY_VOICE_INPUT !== '0') {
        setTimeout(() => {
          log('starting voice input (Hey PARKYY)');
          const ears = spawn(py, ['voice_input.py'], { cwd: ROOT, windowsHide: true });
          ears.stdout.on('data', d => log('[ears]', String(d).trim()));
          ears.stderr.on('data', d => log('[ears]', String(d).trim()));
          ears.on('exit', c => log('voice input exited', c));
        }, 12000); // give the backend a moment first
      }
    } else log('venv python not found at', py);
  }
}

let win = null, tray = null, front = false;

// ---- which screen PARKYY lives on (remembered in desktop/settings.json) ----
const SETTINGS = path.join(__dirname, 'settings.json');
function loadSettings() { try { return JSON.parse(fs.readFileSync(SETTINGS, 'utf8')); } catch (_) { return {}; } }
function saveSettings(s) { try { fs.writeFileSync(SETTINGS, JSON.stringify(s, null, 2)); } catch (_) {} }
function targetDisplay() {
  const all = screen.getAllDisplays();
  const idx = loadSettings().display;
  if (Number.isInteger(idx) && all[idx]) return all[idx];
  // Saud's choice: PARKYY lives on the 2nd screen whenever one is plugged in, so it stays out of the way
  const primary = screen.getPrimaryDisplay();
  return all.find(d => d.id !== primary.id) || primary;
}
function moveToDisplay(which) {
  const all = screen.getAllDisplays();
  const primary = screen.getPrimaryDisplay();
  const cur = win ? screen.getDisplayMatching(win.getBounds()) : primary;
  let idx = all.findIndex(d => d.id === cur.id);
  if (which === 'next') idx = (idx + 1) % all.length;
  else if (which === 'main') idx = all.findIndex(d => d.id === primary.id);
  else if (Number.isInteger(which)) idx = which - 1;
  if (idx < 0 || idx >= all.length) return { ok: false, count: all.length };
  const d = all[idx];
  if (win) win.setBounds(d.workArea);
  const s = loadSettings(); s.display = idx; saveSettings(s);
  return { ok: true, index: idx + 1, count: all.length, main: d.id === primary.id,
           size: `${d.size.width}x${d.size.height}` };
}

function createWindow() {
  const { workArea } = targetDisplay();
  win = new BrowserWindow({
    x: workArea.x, y: workArea.y, width: workArea.width, height: workArea.height,
    frame: false, transparent: true, resizable: false, movable: false,
    skipTaskbar: true, hasShadow: false, focusable: true, show: false,
    backgroundColor: '#00000000',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: false }
  });
  win.loadFile(path.join(__dirname, 'index.html'));
  win.setIgnoreMouseEvents(true, { forward: true });   // clicks pass through to the desktop
  win.once('ready-to-show', () => win.showInactive());
}

function summon() {
  if (!win) return;
  front = true;
  win.setAlwaysOnTop(true, 'floating');
  win.show(); win.focus();
  win.webContents.send('pk:summon');
}
function sendBack() {
  if (!win) return;
  front = false;
  win.setAlwaysOnTop(false);
  win.blur();
}

function makeTray() {
  // tiny blue dot icon generated in code, so no image file is needed
  const px = 16, buf = Buffer.alloc(px * px * 4);
  for (let y = 0; y < px; y++) for (let x = 0; x < px; x++) {
    const i = (y * px + x) * 4, d = Math.hypot(x - 7.5, y - 7.5);
    if (d < 7) { buf[i] = 255; buf[i + 1] = 123; buf[i + 2] = 61; buf[i + 3] = 255; } // BGRA: #3D7BFF
  }
  tray = new Tray(nativeImage.createFromBitmap(buf, { width: px, height: px }));
  tray.setToolTip('PARKYY — Ctrl+Space');
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Show PARKYY  (Ctrl+Space)', click: summon },
    { label: 'Send to back', click: sendBack },
    { label: 'Move to next screen', click: () => moveToDisplay('next') },
    ...roam.menuItems(),
    { label: 'Lock PARKYY', click: () => win && win.webContents.send('pk:lock') },
    { type: 'separator' },
    { label: 'Start with Windows', type: 'checkbox', checked: app.getLoginItemSettings().openAtLogin,
      click: i => app.setLoginItemSettings({ openAtLogin: i.checked, path: process.execPath, args: [__dirname] }) },
    { label: 'Quit PARKYY', click: () => app.quit() }
  ]));
  tray.on('click', () => (front ? sendBack() : summon()));
}

if (!app.requestSingleInstanceLock()) { app.quit(); }
else {
  // starting PARKYY again while it's running = refresh the screen (picks up updates) and show it
  app.on('second-instance', () => { if (win) win.webContents.reloadIgnoringCache(); setTimeout(summon, 1500); });
  app.whenReady().then(async () => {
    app.setLoginItemSettings({ openAtLogin: true, path: process.execPath, args: [__dirname] });
    await startServices();
    createWindow();
    makeTray();
    roam.start();
    globalShortcut.register('Control+Space', () => (front ? sendBack() : summon()));
    ipcMain.on('pk:clickable', (_e, on) => win && win.setIgnoreMouseEvents(!on, { forward: true }));
    ipcMain.on('pk:back', sendBack);
    ipcMain.handle('pk:display', (_e, which) => moveToDisplay(which));
    ipcMain.on('pk:show', () => { if (win && !win.isVisible()) win.showInactive(); });
    screen.on('display-metrics-changed', () => {
      const { workArea } = targetDisplay(); win && win.setBounds(workArea); roam.refreshBounds();
    });
  });
  app.on('will-quit', () => { globalShortcut.unregisterAll(); roam.stop(); if (backend) backend.kill(); });
  app.on('window-all-closed', e => e.preventDefault && e.preventDefault());
}

module.exports = { TOKEN };

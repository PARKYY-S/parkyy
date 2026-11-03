// PARKYY roaming the whole desktop (main-process side).
// The character is ONE PARKYY: while roaming, the big face inside the PARKYY window steps aside and this
// see-through, always-on-top layer (roam.html) shows him walking on your windows / flying, on the screen you work on.
//  - the layer never takes keyboard focus; only PARKYY himself catches clicks, the rest of the screen is click-through
//  - it learns where your windows are (position + size only; titles are NOT sent, only a yes/no "document open")
//  - it mirrors what PARKYY is doing (listening / thinking / speaking) and shows what he says in a bubble
// Off: tray menu "Roam on desktop", or start PARKYY with PARKYY_PET=0.
const { BrowserWindow, screen, ipcMain, powerMonitor } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

module.exports = function createRoam({ log, getWin, summon }) {
  const SETTINGS = path.join(__dirname, 'settings.json');
  const load = () => { try { return JSON.parse(fs.readFileSync(SETTINGS, 'utf8')); } catch (_) { return {}; } };
  const save = s => { try { fs.writeFileSync(SETTINGS, JSON.stringify(s, null, 2)); } catch (_) {} };
  let enabled = process.env.PARKYY_PET !== '0' && load().roam !== false;
  let ov = null, tracker = null, idleTimer = null, lastMood = null;

  const hud = (ch, ...a) => { const w = getWin(); if (w && !w.isDestroyed()) w.webContents.send(ch, ...a); };
  const toOv = (ch, ...a) => { if (ov && !ov.isDestroyed()) ov.webContents.send(ch, ...a); };
  function display() {
    const all = screen.getAllDisplays(), i = load().roamDisplay;
    if (Number.isInteger(i) && all[i]) return all[i];
    return screen.getPrimaryDisplay();               // the screen you actually work on
  }

  function toLocal(d) {
    try {
      const wb = ov.getBounds();
      const a = screen.screenToDipPoint({ x: d.x, y: d.y });
      const b = screen.screenToDipPoint({ x: d.x + d.w, y: d.y + d.h });
      return { id: d.id, x: a.x - wb.x, y: a.y - wb.y, w: b.x - a.x, h: b.y - a.y, max: !!d.max, min: !!d.min, reading: !!d.reading };
    } catch (_) { return { none: true }; }
  }
  function startTracker() {
    if (tracker || process.platform !== 'win32') return;
    const ps = path.join(__dirname, 'fgwin.ps1');
    if (!fs.existsSync(ps)) { log('roam: fgwin.ps1 missing - PARKYY will walk along the bottom of the screen only'); return; }
    tracker = spawn('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden', '-File', ps], { windowsHide: true });
    let buf = '';
    tracker.stdout.on('data', c => {
      buf += c.toString('utf8');
      let i;
      while ((i = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
        if (!line || !ov) continue;
        try { const d = JSON.parse(line); toOv('pet:fg', d.none ? { none: true } : toLocal(d)); } catch (_) {}
      }
    });
    tracker.stderr.on('data', c => log('[roam-fg]', String(c).trim().slice(0, 200)));
    tracker.on('exit', code => { tracker = null; log('roam: window tracker exited', code); });
  }
  function stopTracker() { if (tracker) { try { tracker.kill(); } catch (_) {} tracker = null; } }

  function create() {
    if (ov) return;
    const wa = display().workArea;
    ov = new BrowserWindow({
      x: wa.x, y: wa.y, width: wa.width, height: wa.height,
      frame: false, transparent: true, resizable: false, movable: false, skipTaskbar: true, hasShadow: false,
      focusable: false, show: false, alwaysOnTop: true, backgroundColor: '#00000000',
      webPreferences: { preload: path.join(__dirname, 'pet-preload.js'), contextIsolation: true, sandbox: false }
    });
    ov.setAlwaysOnTop(true, 'screen-saver');
    ov.setIgnoreMouseEvents(true, { forward: true });
    ov.loadFile(path.join(__dirname, 'roam.html'));
    ov.once('ready-to-show', () => ov && ov.showInactive());
    ov.webContents.on('did-finish-load', () => { if (lastMood) toOv('pet:mood', ...lastMood); });
    ov.on('closed', () => { ov = null; });
    if (!idleTimer) idleTimer = setInterval(() => toOv('pet:idle', powerMonitor.getSystemIdleTime()), 3000);
    startTracker();
    hud('pk:overlay', true);
  }
  function destroy() {
    stopTracker();
    if (idleTimer) { clearInterval(idleTimer); idleTimer = null; }
    if (ov) { try { ov.destroy(); } catch (_) {} ov = null; }
    hud('pk:overlay', false);                          // the big face in the PARKYY window is back
  }
  function setEnabled(on) {
    enabled = !!on; const s = load(); s.roam = enabled; save(s);
    if (enabled) create(); else destroy();
  }
  function nextScreen() {
    const all = screen.getAllDisplays(); if (all.length < 2) return;
    const cur = all.findIndex(d => d.id === display().id);
    const s = load(); s.roamDisplay = (cur + 1) % all.length; save(s);
    refreshBounds(); if (ov) ov.reload();
  }
  function refreshBounds() { if (ov) { const wa = display().workArea; ov.setBounds({ x: wa.x, y: wa.y, width: wa.width, height: wa.height }); } }

  ipcMain.handle('pk:overlayget', () => enabled && !!ov);
  ipcMain.on('pet:clickable', (_e, on) => ov && ov.setIgnoreMouseEvents(!on, { forward: true }));
  ipcMain.on('pet:summon', () => summon());
  ipcMain.on('pet:hide', () => setEnabled(false));
  ipcMain.handle('pet:roamget', () => true);
  ipcMain.on('pk:mood', (_e, m, sub, st) => { lastMood = [String(m || ''), String(sub || '').slice(0, 120), String(st || '')]; toOv('pet:mood', ...lastMood); });
  ipcMain.on('pk:petsay', (_e, t) => toOv('pet:say', String(t || '').slice(0, 140)));

  return {
    start() { if (enabled) create(); },
    stop() { stopTracker(); if (idleTimer) clearInterval(idleTimer); if (ov) { try { ov.destroy(); } catch (_) {} ov = null; } },
    refreshBounds,
    menuItems() {
      return [
        { label: 'Roam on desktop (walk & fly)', type: 'checkbox', checked: enabled, click: i => setEnabled(i.checked) },
        { label: 'Move roaming to other screen', click: nextScreen }
      ];
    }
  };
};

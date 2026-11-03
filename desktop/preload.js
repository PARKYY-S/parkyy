// Bridges the PARKYY page to Windows (click-through, Ctrl+Space, token).
const { contextBridge, ipcRenderer } = require('electron');
const fs = require('fs');
const path = require('path');

function readToken() {
  try {
    const env = fs.readFileSync(path.join(__dirname, '..', '.env'), 'utf8');
    const m = env.match(/^\s*PARKYY_AUTH_TOKEN\s*=\s*(.+)\s*$/m);
    if (m) return m[1].trim().replace(/^["']|["']$/g, '');
  } catch (_) {}
  return 'parkyy-local';
}

contextBridge.exposeInMainWorld('pk', {
  token: readToken(),
  api: 'http://127.0.0.1:8000',
  setClickable: on => ipcRenderer.send('pk:clickable', !!on),
  sendBack: () => ipcRenderer.send('pk:back'),
  show: () => ipcRenderer.send('pk:show'),
  moveDisplay: which => ipcRenderer.invoke('pk:display', which),
  onSummon: fn => ipcRenderer.on('pk:summon', fn),
  onLock: fn => ipcRenderer.on('pk:lock', fn),
  // tell the roaming PARKYY on the desktop what's happening; hide the big face while he roams
  mood: (m, sub, st) => ipcRenderer.send('pk:mood', m, sub, st),
  petSay: t => ipcRenderer.send('pk:petsay', t),
  onOverlay: fn => ipcRenderer.on('pk:overlay', (_e, on) => fn(on)),
  overlayGet: () => ipcRenderer.invoke('pk:overlayget')
});

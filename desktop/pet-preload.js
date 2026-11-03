// Bridge for PARKYY's roaming layer (roam.html). Exposed as window.pk in that page only.
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('pk', {
  setClickable: on => ipcRenderer.send('pet:clickable', !!on),
  summon: () => ipcRenderer.send('pet:summon'),
  hide: () => ipcRenderer.send('pet:hide'),
  onFg: fn => ipcRenderer.on('pet:fg', (_e, d) => fn(d)),
  onIdle: fn => ipcRenderer.on('pet:idle', (_e, s) => fn(s)),
  onMood: fn => ipcRenderer.on('pet:mood', (_e, m, sub, st) => fn(m, sub, st)),
  onSay: fn => ipcRenderer.on('pet:say', (_e, t) => fn(t)),
  onRoam: () => {},
  roamGet: () => ipcRenderer.invoke('pet:roamget')
});

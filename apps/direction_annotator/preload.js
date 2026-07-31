const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  selectFolder: () => ipcRenderer.invoke('select-folder'),
  getDataRoot: () => ipcRenderer.invoke('get-data-root'),
  setDataRoot: (path) => ipcRenderer.invoke('set-data-root', path),
  getServerPort: () => ipcRenderer.invoke('get-server-port'),
});

'use strict';
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('svfMaker', {
  pickFiles:        () => ipcRenderer.invoke('maker:pick-files'),      // Promise<string[]>   ([] when cancelled)
  pickFolder:       () => ipcRenderer.invoke('maker:pick-folder'),     // Promise<string[]>   ([] or [dir])
  pickOutputDir:    () => ipcRenderer.invoke('maker:pick-output-dir'), // Promise<string|null>
  openOutputFolder: () => ipcRenderer.invoke('maker:open-output'),     // Promise<void>; takes no argument
  platform: process.platform,                                          // "linux" | "darwin" | "win32"
});

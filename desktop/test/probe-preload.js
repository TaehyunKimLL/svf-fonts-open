'use strict';
// Test only (loaded by the e2e's second window): lets a page call any IPC channel so the main process's sender check
// can be seen refusing it.
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('probeInvoke', (channel) => ipcRenderer.invoke(channel));

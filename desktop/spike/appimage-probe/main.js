const { app } = require('electron'); app.whenReady().then(() => { console.log('probe ok'); app.quit(); });

const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('asuraAPI', {
  window: {
    setMode: (expanded) => ipcRenderer.invoke('window:set-mode', expanded),
    closePopup: () => ipcRenderer.invoke('window:close-popup')
  },
  config: {
    get: () => ipcRenderer.invoke('config:get'),
    set: (patch) => ipcRenderer.invoke('config:set', patch)
  },
  auth: {
    getUser: () => ipcRenderer.invoke('session:get-user'),
    login: (credentials) => ipcRenderer.invoke('auth:login', credentials),
    logout: () => ipcRenderer.invoke('auth:logout')
  },
  api: {
    call: (request) => ipcRenderer.invoke('api:call', request)
  },
  email: {
    openCompose: (options) => ipcRenderer.invoke('email:open-compose', options)
  },
  printer: {
    list: () => ipcRenderer.invoke('printer:list'),
    printRequest: (options) => ipcRenderer.invoke('printer:print-request', options),
    printPdf: (options) => ipcRenderer.invoke('printer:print-pdf', options)
  },
  notifications: {
    show: (title, body) => ipcRenderer.invoke('notifications:show', title, body)
  },
  app: {
    quit: () => ipcRenderer.invoke('app:quit')
  }
});

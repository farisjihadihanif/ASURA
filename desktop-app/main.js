const { app, BrowserWindow, ipcMain, nativeImage, screen, shell, Tray, Menu, Notification } = require('electron');
const path = require('node:path');
const os = require('node:os');
const fs = require('node:fs');
const fsp = require('node:fs/promises');
app.disableHardwareAcceleration();
let mainWindow;
let tray;
let isExpanded = false;
const API_BASE_URL = (process.env.ASURA_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '');
const SESSION_FILE = path.join(app.getPath('userData'), 'asura-session.json');
function readSession() {
  try {
    if (fs.existsSync(SESSION_FILE)) {
      return JSON.parse(fs.readFileSync(SESSION_FILE, 'utf8'));
    }
  } catch {}
  return { access: null, refresh: null, user: null };
}
function writeSession(data) {
  try {
    fs.mkdirSync(path.dirname(SESSION_FILE), { recursive: true });
    fs.writeFileSync(SESSION_FILE, JSON.stringify(data, null, 2), 'utf8');
  } catch (err) {
    console.error('[ASURA] Gagal menyimpan sesi:', err);
  }
}
function clearSession() {
  try {
    if (fs.existsSync(SESSION_FILE)) fs.unlinkSync(SESSION_FILE);
  } catch {}
}
function extractApiError(payload, fallback) {
  if (!payload || typeof payload !== 'object') return fallback;
  if (typeof payload.detail === 'string') return payload.detail;
  if (typeof payload.message === 'string') return payload.message;
  if (typeof payload.error === 'string') return payload.error;
  if (payload.errors && typeof payload.errors === 'object') {
    const firstKey = Object.keys(payload.errors)[0];
    const val = payload.errors[firstKey];
    if (Array.isArray(val) && val[0]) return `${firstKey}: ${val[0]}`;
    if (typeof val === 'string') return `${firstKey}: ${val}`;
  }
  return fallback;
}
async function callBackend({ method = 'GET', endpoint, path: reqPath, body }) {
  const targetPath = endpoint || reqPath || '/';
  const url = targetPath.startsWith('http') ? targetPath : `${API_BASE_URL}${targetPath.startsWith('/') ? '' : '/'}${targetPath}`;
  const session = readSession();
  const headers = { 'Content-Type': 'application/json' };
  if (session.access) {
    headers['Authorization'] = `Bearer ${session.access}`;
  }
  const doFetch = async (hdrs) => {
    const opts = { method: method.toUpperCase(), headers: hdrs };
    if (body !== undefined && opts.method !== 'GET' && opts.method !== 'HEAD') {
      opts.body = typeof body === 'string' ? body : JSON.stringify(body);
    }
    return fetch(url, opts);
  };
  let res;
  for (let attempt = 0; attempt < 5; attempt++) {
    try {
      res = await doFetch(headers);
      break;
    } catch (netErr) {
      if (attempt === 4) throw netErr;
      await new Promise((r) => setTimeout(r, 1000));
    }
  }
  if (res.status === 401 && session.refresh) {
    try {
      const refRes = await fetch(`${API_BASE_URL}/api/accounts/token/refresh/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh: session.refresh }),
      });
      if (refRes.ok) {
        const refData = await refRes.json();
        if (refData.access) {
          session.access = refData.access;
          writeSession(session);
          headers['Authorization'] = `Bearer ${refData.access}`;
          res = await doFetch(headers);
        }
      }
    } catch {}
  }
  const text = await res.text();
  let parsed = null;
  try {
    parsed = text ? JSON.parse(text) : {};
  } catch {
    parsed = { detail: text };
  }
  if (!res.ok) {
    throw new Error(extractApiError(parsed, `HTTP ${res.status}`));
  }
  return parsed;
}
const isAllowedExternalUrl = (value) => {
  try { return new URL(value).protocol === 'https:'; } catch { return false; }
};
function widgetBounds(expanded) {
  const display = screen.getPrimaryDisplay();
  const { x, y, width, height } = display.workArea;
  const windowWidth = expanded ? Math.min(440, width - 32) : 180;
  const windowHeight = expanded ? Math.min(720, height - 32) : 190;
  return { width: windowWidth, height: windowHeight, x: x + width - windowWidth - 24, y: y + height - windowHeight - 24 };
}
function resizeWidget(expanded) {
  isExpanded = expanded;
  if (!mainWindow) return;
  mainWindow.setBounds(widgetBounds(expanded), true);
  mainWindow.setIgnoreMouseEvents(false);
  mainWindow.focus();
  if (expanded) mainWindow.show();
}
function assertTrustedSender(event) {
  const senderUrl = event.senderFrame?.url || '';
  if (!senderUrl.startsWith('file://')) throw new Error('Sumber IPC tidak dipercaya.');
}
async function createWindow() {
  mainWindow = new BrowserWindow({
    ...widgetBounds(false),
    transparent: true,
    backgroundColor: '#00000000',
    frame: false,
    resizable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    show: false,
    hasShadow: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true
    }
  });
  mainWindow.setAlwaysOnTop(true, 'floating');
  mainWindow.setIgnoreMouseEvents(false);
  mainWindow.loadFile(path.join(__dirname, 'index.html'));
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (isAllowedExternalUrl(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
  mainWindow.webContents.on('will-navigate', (event) => event.preventDefault());
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    mainWindow.focus();
  });
}
async function printPdfDirectToPrinter(requestId, deviceName = '') {
  const res = await callBackend({
    method: 'GET',
    endpoint: `/api/surat/requests/${requestId}/preview-pdf/?format=base64`,
  });
  if (!res || !res.pdf_base64) {
    throw new Error('Dokumen PDF surat belum tersedia untuk dicetak.');
  }
  const tempPdfPath = path.join(os.tmpdir(), `asura_print_${requestId}_${Date.now()}.pdf`);
  await fsp.writeFile(tempPdfPath, Buffer.from(res.pdf_base64, 'base64'));
  const printWin = new BrowserWindow({
    show: false,
    webPreferences: {
      plugins: true,
      paintWhenInitiallyHidden: true,
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  try {
    await printWin.loadFile(tempPdfPath);
    await new Promise((resolve) => setTimeout(resolve, 1200));
    await new Promise((resolve, reject) => {
      const printOpts = {
        silent: Boolean(deviceName),
        printBackground: true,
      };
      if (deviceName) {
        printOpts.deviceName = deviceName;
      }
      printWin.webContents.print(printOpts, (success, failureReason) => {
        if (!success && failureReason && failureReason !== 'cancelled') {
          reject(new Error(`Gagal mencetak ke printer: ${failureReason}`));
        } else {
          resolve(success);
        }
      });
    });
    return { printed: true, deviceName: deviceName || 'Dialog Printer Windows' };
  } finally {
    if (!printWin.isDestroyed()) {
      printWin.close();
    }
    setTimeout(() => {
      fsp.unlink(tempPdfPath).catch(() => {});
    }, 5000);
  }
}
function registerIpc() {
  ipcMain.handle('window:set-mode', (event, expanded) => { assertTrustedSender(event); resizeWidget(Boolean(expanded)); });
  ipcMain.handle('window:close-popup', (event) => { assertTrustedSender(event); resizeWidget(false); });
  ipcMain.handle('config:get', (event) => { assertTrustedSender(event); return { apiBaseUrl: API_BASE_URL, demoAccounts: true }; });
  ipcMain.handle('config:set', (event) => { assertTrustedSender(event); return { apiBaseUrl: API_BASE_URL, demoAccounts: true }; });
  ipcMain.handle('session:get-user', (event) => { assertTrustedSender(event); return readSession().user || null; });
  ipcMain.handle('auth:login', async (event, credentials) => {
    assertTrustedSender(event);
    const result = await callBackend({
      method: 'POST',
      endpoint: '/api/accounts/login/',
      body: credentials,
    });
    writeSession({
      access: result.access,
      refresh: result.refresh,
      user: result.user,
    });
    return result.user;
  });
  ipcMain.handle('auth:logout', async (event) => {
    assertTrustedSender(event);
    const s = readSession();
    try {
      if (s.refresh) {
        await callBackend({ method: 'POST', endpoint: '/api/accounts/logout/', body: { refresh: s.refresh } });
      }
    } catch {} finally {
      clearSession();
    }
  });
  ipcMain.handle('api:call', async (event, request) => { assertTrustedSender(event); return callBackend(request); });
  ipcMain.handle('email:open-compose', async (event, options) => {
    assertTrustedSender(event);
    const subject = encodeURIComponent(options.subject || 'Surat ASURA');
    const body = encodeURIComponent(options.body || '');
    await shell.openExternal(`mailto:${encodeURIComponent(options.to || '')}?subject=${subject}&body=${body}`);
    return { mode: 'mailto' };
  });
  ipcMain.handle('printer:list', async (event) => {
    assertTrustedSender(event);
    if (!mainWindow) return [];
    return mainWindow.webContents.getPrintersAsync();
  });
  ipcMain.handle('printer:print-request', async (event, { requestId, deviceName }) => {
    assertTrustedSender(event);
    return printPdfDirectToPrinter(requestId, deviceName);
  });
  ipcMain.handle('printer:print-pdf', async (event, { filePath, requestId, deviceName }) => {
    assertTrustedSender(event);
    if (requestId) return printPdfDirectToPrinter(requestId, deviceName);
    if (!filePath) throw new Error('Berkas PDF tidak ditemukan.');
    await shell.openPath(filePath);
    return { mode: 'open-pdf' };
  });
  ipcMain.handle('notifications:show', (event, payload, bodyArg) => {
    assertTrustedSender(event);
    const title = typeof payload === 'object' ? payload.title : payload;
    const body = typeof payload === 'object' ? payload.body : bodyArg;
    if (Notification.isSupported()) new Notification({ title: String(title || 'ASURA'), body: String(body || '') }).show();
  });
  ipcMain.handle('app:quit', (event) => { assertTrustedSender(event); app.quit(); });
}
function createTray() {
  const iconPath = path.join(__dirname, 'assets', 'asura-mascot.png');
  const trayIcon = fs.existsSync(iconPath) ? nativeImage.createFromPath(iconPath).resize({ width: 16, height: 16 }) : nativeImage.createEmpty();
  tray = new Tray(trayIcon);
  tray.setToolTip('ASURA');
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Tampilkan ASURA', click: () => { mainWindow.show(); resizeWidget(true); } },
    { label: 'Sembunyikan', click: () => mainWindow.hide() },
    { type: 'separator' },
    { label: 'Keluar', click: () => app.quit() }
  ]));
}
app.on('window-all-closed', (event) => event.preventDefault());
process.on('uncaughtException', (error) => console.error('[ASURA] uncaughtException', error));
process.on('unhandledRejection', (error) => console.error('[ASURA] unhandledRejection', error));
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) app.quit();
else {
  app.on('second-instance', () => { if (mainWindow) { mainWindow.show(); mainWindow.focus(); } });
  app.whenReady().then(async () => {
    registerIpc();
    createTray();
    await createWindow();
  });
}




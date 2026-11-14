const { app, BrowserWindow, ipcMain, nativeImage, screen, shell, Tray, Menu, Notification } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const http = require('node:http');
app.disableHardwareAcceleration();
let mainWindow;
let tray;
let localBridgeServer;
let isExpanded = false;
let suppressAutoCollapse = false;
let suppressUntil = 0;
function holdCollapse(ms = 5000) {
  suppressUntil = Date.now() + ms;
}
let blurCollapseTimer = null;
const API_BASE_URL = (process.env.ASURA_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '');
const SESSION_FILE = path.join(app.getPath('userData'), 'asura-session.json');
const PRINT_BRIDGE_PORT = 38911;
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
function withActiveAccount(session) {
  const accounts = (session.accounts || []).filter((a) => a.user?.nip_nim !== session.user?.nip_nim);
  if (session.user && session.access) {
    accounts.unshift({ access: session.access, refresh: session.refresh, user: session.user });
  }
  return { ...session, accounts: accounts.slice(0, 5) };
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
  const windowWidth = expanded ? Math.min(440, width - 32) : 170;
  const windowHeight = expanded ? Math.min(720, height - 32) : 185;
  return {
    width: windowWidth,
    height: windowHeight,
    x: x + width - windowWidth - 20,
    y: y + height - windowHeight - 20,
  };
}
function resizeWidget(expanded) {
  isExpanded = Boolean(expanded);
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.setBounds(widgetBounds(isExpanded), false);
  mainWindow.setIgnoreMouseEvents(false);
  mainWindow.show();
  if (isExpanded) {
    mainWindow.focus();
  }
}
function collapseToMascot() {
  if (!isExpanded) return;
  resizeWidget(false);
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('widget:auto-collapsed');
  }
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
      webSecurity: true,
    },
  });
  mainWindow.setAlwaysOnTop(true, 'floating');
  mainWindow.setIgnoreMouseEvents(false);
  mainWindow.loadFile(path.join(__dirname, 'index.html'));
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (isAllowedExternalUrl(url)) { holdCollapse(); shell.openExternal(url); }
    return { action: 'deny' };
  });
  mainWindow.webContents.on('will-navigate', (event) => event.preventDefault());
  // Ketika user klik di luar area chat pop-up, otomatis minimize kembali ke ikon maskot
  mainWindow.on('blur', () => {
    if (blurCollapseTimer) clearTimeout(blurCollapseTimer);
    blurCollapseTimer = setTimeout(() => {
      if (isExpanded && !suppressAutoCollapse && Date.now() >= suppressUntil && mainWindow && !mainWindow.isFocused()) {
        collapseToMascot();
      }
    }, 150);
  });
  mainWindow.on('focus', () => {
    if (blurCollapseTimer) {
      clearTimeout(blurCollapseTimer);
      blurCollapseTimer = null;
    }
  });
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });
}
async function resolveTargetPrinter(preferredDeviceName = '') {
  if (!mainWindow) return { name: preferredDeviceName || '', isVirtual: false };
  const printers = await mainWindow.webContents.getPrintersAsync();
  if (!Array.isArray(printers) || printers.length === 0) {
    return { name: preferredDeviceName || '', isVirtual: false };
  }
  const isVirtualName = (n) => /pdf|xps|onenote|fax|webex/i.test(n || '');
  if (preferredDeviceName) {
    const exact = printers.find((p) => p.name === preferredDeviceName);
    if (exact) return { name: exact.name, isVirtual: isVirtualName(exact.name) };
  }
  const physicalDefault = printers.find((p) => p.isDefault && !isVirtualName(p.name));
  if (physicalDefault) return { name: physicalDefault.name, isVirtual: false };
  const anyPhysical = printers.find((p) => !isVirtualName(p.name));
  if (anyPhysical) return { name: anyPhysical.name, isVirtual: false };
  const msPdf = printers.find((p) => /microsoft print to pdf/i.test(p.name));
  if (msPdf) return { name: msPdf.name, isVirtual: true };
  const safeFallback = printers.find((p) => !/adobe pdf/i.test(p.name)) || printers[0];
  return { name: safeFallback.name, isVirtual: isVirtualName(safeFallback.name) };
}
async function printPdfDirectToPrinter(requestId, deviceName = '') {
  const res = await callBackend({
    method: 'GET',
    endpoint: `/api/surat/requests/${requestId}/preview-pdf/?encoding=base64`,
  });
  if (!res || (!res.print_html && !res.pdf_base64)) {
    throw new Error('Dokumen surat belum tersedia untuk dicetak.');
  }
  const targetPrinter = await resolveTargetPrinter(deviceName);
  const printableHtml = res.print_html || `<!doctype html><html><body style="font-family:serif;padding:40px;"><h2>Dokumen Resmi ASURA</h2><p>ID Surat: ${requestId}</p></body></html>`;
  const printWin = new BrowserWindow({
    width: 794,
    height: 1123,
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      paintWhenInitiallyHidden: true,
    },
  });
  try {
    await printWin.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(printableHtml)}`);
    await new Promise((resolve) => setTimeout(resolve, 400));
    await new Promise((resolve, reject) => {
      const printOpts = {
        silent: true,
        printBackground: true,
        pageSize: 'A4',
      };
      if (targetPrinter.name) {
        printOpts.deviceName = targetPrinter.name;
      }
      printWin.webContents.print(printOpts, (success, failureReason) => {
        if (!success && failureReason && failureReason !== 'cancelled') {
          reject(new Error(`Gagal mencetak ke printer (${targetPrinter.name || 'Default'}): ${failureReason}`));
        } else {
          resolve(success);
        }
      });
    });
    return { printed: true, deviceName: targetPrinter.name || 'Printer Default' };
  } finally {
    if (!printWin.isDestroyed()) {
      printWin.close();
    }
  }
}
function startLocalPrintBridge() {
  localBridgeServer = http.createServer((req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, GET, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    if (req.method === 'OPTIONS') {
      res.writeHead(204);
      res.end();
      return;
    }
    if (req.method === 'GET' && req.url === '/health') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ ok: true, agent: 'ASURA Print Bridge' }));
      return;
    }
    if (req.method === 'POST' && req.url === '/print') {
      let bodyStr = '';
      req.on('data', (chunk) => { bodyStr += chunk; });
      req.on('end', async () => {
        try {
          const payload = bodyStr ? JSON.parse(bodyStr) : {};
          const requestId = Number(payload.requestId);
          if (!requestId) {
            res.writeHead(400, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'requestId wajib diisi.' }));
            return;
          }
          const result = await printPdfDirectToPrinter(requestId, payload.deviceName || '');
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify(result));
        } catch (err) {
          res.writeHead(500, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: err.message || 'Gagal mencetak dokumen.' }));
        }
      });
      return;
    }
    res.writeHead(404);
    res.end();
  });
  localBridgeServer.on('error', (err) => {
    console.warn('[ASURA] Local print bridge port warning:', err.message);
  });
  localBridgeServer.listen(PRINT_BRIDGE_PORT, '127.0.0.1');
}
function registerIpc() {
  ipcMain.handle('window:set-mode', (event, expanded) => { assertTrustedSender(event); resizeWidget(Boolean(expanded)); });
  ipcMain.handle('window:close-popup', (event) => { assertTrustedSender(event); resizeWidget(false); });
  ipcMain.handle('window:set-auto-close-lock', (event, locked) => { assertTrustedSender(event); suppressAutoCollapse = Boolean(locked); });
  ipcMain.handle('config:get', (event) => { assertTrustedSender(event); return { apiBaseUrl: API_BASE_URL, demoAccounts: !app.isPackaged }; });
  ipcMain.handle('config:set', (event) => { assertTrustedSender(event); return { apiBaseUrl: API_BASE_URL, demoAccounts: !app.isPackaged }; });
  ipcMain.handle('session:get-user', (event) => { assertTrustedSender(event); return readSession().user || null; });
  ipcMain.handle('auth:login', async (event, credentials) => {
    assertTrustedSender(event);
    const result = await callBackend({
      method: 'POST',
      endpoint: '/api/accounts/login/',
      body: credentials,
    });
    const prev = readSession();
    writeSession(withActiveAccount({
      access: result.access,
      refresh: result.refresh,
      user: result.user,
      accounts: prev.accounts || [],
    }));
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
      const rest = (s.accounts || []).filter((a) => a.user?.nip_nim !== s.user?.nip_nim);
      if (rest.length) writeSession({ access: null, refresh: null, user: null, accounts: rest });
      else clearSession();
    }
  });
  ipcMain.handle('auth:register-lookup', async (event, nipNim) => {
    assertTrustedSender(event);
    const res = await callBackend({
      method: 'GET',
      endpoint: `/api/accounts/register/lookup/?nip_nim=${encodeURIComponent(String(nipNim || '').trim())}`,
    });
    return res.data || res;
  });
  ipcMain.handle('auth:register', async (event, payload) => {
    assertTrustedSender(event);
    const result = await callBackend({
      method: 'POST',
      endpoint: '/api/accounts/register/',
      body: { nip_nim: payload.nip_nim, email: payload.email, password: payload.password },
    });
    const prev = readSession();
    writeSession(withActiveAccount({
      access: result.access,
      refresh: result.refresh,
      user: result.user,
      accounts: prev.accounts || [],
    }));
    return result.user;
  });
  ipcMain.handle('auth:list-accounts', (event) => {
    assertTrustedSender(event);
    const s = withActiveAccount(readSession());
    return s.accounts.map((a) => ({
      nip_nim: a.user.nip_nim,
      nama: a.user.nama,
      role: a.user.role,
      active: a.user.nip_nim === readSession().user?.nip_nim,
    }));
  });
  ipcMain.handle('auth:add-account', (event) => {
    assertTrustedSender(event);
    const s = withActiveAccount(readSession());
    writeSession({ access: null, refresh: null, user: null, accounts: s.accounts });
    return true;
  });
  ipcMain.handle('auth:switch-account', async (event, nipNim) => {
    assertTrustedSender(event);
    const s = withActiveAccount(readSession());
    const target = s.accounts.find((a) => a.user.nip_nim === nipNim);
    if (!target) throw new Error('Akun tidak ditemukan.');
    writeSession({ access: target.access, refresh: target.refresh, user: target.user, accounts: s.accounts });
    try {
      const me = await callBackend({ method: 'GET', endpoint: '/api/accounts/me/' });
      const cur = readSession();
      writeSession(withActiveAccount({ ...cur, user: me && me.nip_nim ? { ...cur.user, ...me } : cur.user }));
      return readSession().user;
    } catch {
      const rest = s.accounts.filter((a) => a.user.nip_nim !== nipNim);
      writeSession({ access: null, refresh: null, user: null, accounts: rest });
      throw new Error('Sesi akun sudah kedaluwarsa, silakan masuk lagi.');
    }
  });
  ipcMain.handle('api:call', async (event, request) => { assertTrustedSender(event); return callBackend(request); });
  ipcMain.handle('email:open-compose', async (event, options) => {
    assertTrustedSender(event);
    const subject = encodeURIComponent(options.subject || 'Surat ASURA');
    const body = encodeURIComponent(options.body || '');
    holdCollapse(15000);
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
    { label: 'Keluar', click: () => app.quit() },
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
    startLocalPrintBridge();
    createTray();
    await createWindow();
  });
}

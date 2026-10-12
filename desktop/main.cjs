'use strict';
const { app, BrowserWindow, Menu, dialog, shell } = require('electron');
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const path = require('node:path');
const http = require('node:http');
const net = require('node:net');
const { spawn } = require('node:child_process');

const smokeArg = process.argv.find(arg => arg.startsWith('--smoke-test='));
const smokePath = smokeArg ? path.resolve(smokeArg.slice('--smoke-test='.length)) : null;
app.setName('Laboratorium danych');
// Stable Polish directory name; acceptance runs use their own profile.
const profile = smokePath ? path.join(path.dirname(smokePath), 'smoke-user-data')
  : path.join(app.getPath('appData'), 'Laboratorium danych');
fs.mkdirSync(profile, { recursive: true });
app.setPath('userData', profile);
const locked = app.requestSingleInstanceLock();
let window, server, log, logPath, origin;
let stopping = false;
let failed = false;
let shutdown;

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const writeLog = message => log?.write(`[${new Date().toISOString()}] ${message}\n`);

function freePort() {
  return new Promise((resolve, reject) => {
    const probe = net.createServer();
    probe.once('error', reject);
    probe.listen(0, '127.0.0.1', () => {
      const port = probe.address().port;
      probe.close(error => error ? reject(error) : resolve(port));
    });
  });
}

function healthy(port) {
  return new Promise(resolve => {
    const request = http.get({ host: '127.0.0.1', port, path: '/_stcore/health', timeout: 1000 }, response => {
      response.resume();
      resolve(response.statusCode === 200);
    });
    request.on('timeout', () => request.destroy());
    request.on('error', () => resolve(false));
  });
}

async function stopServer() {
  const pid = server?.pid;
  if (!pid) return;
  if (process.platform === 'win32') {
    await new Promise(resolve => {
      const killer = spawn('taskkill', ['/PID', String(pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
      killer.on('error', resolve);
      killer.on('exit', resolve);
    });
  } else {
    try { process.kill(-pid, 'SIGTERM'); } catch (error) { if (error.code !== 'ESRCH') writeLog(error.message); }
    // Give the entire group time to exit, then remove remaining descendants.
    for (let i = 0; i < 20; i++) {
      try { process.kill(-pid, 0); } catch { return; }
      await delay(100);
    }
    try { process.kill(-pid, 'SIGKILL'); } catch (error) { if (error.code !== 'ESRCH') writeLog(error.message); }
  }
}

function finish(code = 0) {
  if (shutdown) return shutdown;
  stopping = true;
  shutdown = (async () => {
    await stopServer();
    await new Promise(resolve => log ? log.end(resolve) : resolve());
    app.exit(code);
  })();
  return shutdown;
}

async function fail(error) {
  if (stopping || failed) return;
  failed = true;
  writeLog(error.stack || String(error));
  console.error(`Nie można uruchomić Laboratorium danych: ${error.message}. Log: ${logPath || 'niedostępny'}`);
  if (!smokePath) {
    dialog.showErrorBox('Laboratorium danych — błąd uruchomienia',
      `Nie można uruchomić aplikacji. Zamknij ją i spróbuj ponownie.\n\n${error.message}\n\nPlik dziennika: ${logPath || 'Nie udało się utworzyć pliku dziennika.'}`);
  }
  await finish(1);
}

function openExternal(url) {
  try {
    if (['https:', 'http:', 'mailto:'].includes(new URL(url).protocol)) {
      shell.openExternal(url).catch(error => writeLog(`External link: ${error.message}`));
    }
  } catch { /* Ignore invalid URLs. */ }
}

function makeMenu() {
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { label: 'Laboratorium danych', submenu: [
      { label: 'Folder z danymi i ustawieniami', click: () => shell.openPath(app.getPath('userData')).then(error => { if (error) writeLog(error); }) },
      { type: 'separator' },
      { label: 'Zakończ', accelerator: 'CmdOrCtrl+Q', click: () => app.quit() }
    ] },
    { label: 'Widok', submenu: [
      { label: 'Odśwież', role: 'reload' },
      { label: 'Powiększ', role: 'zoomIn' },
      { label: 'Pomniejsz', role: 'zoomOut' },
      { label: 'Rozmiar domyślny', role: 'resetZoom' }
    ] },
    { label: 'Edycja', submenu: [
      { label: 'Cofnij', role: 'undo' }, { label: 'Ponów', role: 'redo' },
      { type: 'separator' },
      { label: 'Wytnij', role: 'cut' }, { label: 'Kopiuj', role: 'copy' },
      { label: 'Wklej', role: 'paste' }, { label: 'Zaznacz wszystko', role: 'selectAll' }
    ] }
  ]));
}

async function captureSmoke() {
  const deadline = Date.now() + 90000;
  while (Date.now() < deadline && !stopping) {
    const rendered = await window.webContents.executeJavaScript(`(() => {
      const title = document.querySelector('h1')?.innerText;
      const tabs = document.querySelectorAll('[role="tab"]').length;
      const inputReady = !!document.querySelector('[data-testid="stTextInput"] input');
      const downloadButtons = document.querySelectorAll('[data-testid="stDownloadButton"] button').length;
      const visibleSkeletons = [...document.querySelectorAll('[data-testid="stSkeleton"], [data-testid="stSkeletonElement"]')].filter(element => {
        const box = element.getBoundingClientRect();
        return box.width > 0 && box.height > 0 && box.top < innerHeight && box.bottom > 0;
      }).length;
      const exceptions = [...document.querySelectorAll('[data-testid="stException"]')].map(e => e.innerText);
      const errors = [...document.querySelectorAll('[data-testid="stAlertContentError"]')].map(e => e.innerText);
      return { title, tabs, inputReady, downloadButtons, visibleSkeletons, exceptions, errors };
    })()`);
    if (rendered.exceptions.length || rendered.errors.length) throw new Error(`Streamlit: ${[...rendered.exceptions, ...rendered.errors].join('; ')}`);
    if (rendered.title === 'Laboratorium danych' && rendered.tabs >= 5 && rendered.inputReady && rendered.downloadButtons >= 3 && rendered.visibleSkeletons === 0) {
      // Allow fonts, data widgets and the final paint to finish.
      await delay(2000);
      const finalErrors = await window.webContents.executeJavaScript(`Array.from(document.querySelectorAll('[data-testid="stException"], [data-testid="stAlertContentError"]'), e => e.innerText)`);
      if (finalErrors.length) throw new Error(`Streamlit: ${finalErrors.join('; ')}`);
      const png = await window.webContents.capturePage();
      await fsp.mkdir(path.dirname(smokePath), { recursive: true });
      await fsp.writeFile(smokePath, png.toPNG());
      console.log(`SMOKE OK: rendered title, ${rendered.tabs} tabs, input and ${rendered.downloadButtons} download controls, no visible loading placeholders; PNG ${smokePath}`);
      writeLog(`SMOKE OK: ${smokePath}`);
      await finish(0);
      return;
    }
    await delay(350);
  }
  if (!stopping) throw new Error('Przekroczono czas oczekiwania na widok aplikacji (90 s).');
}

async function start() {
  const userDir = app.getPath('userData');
  await fsp.mkdir(path.join(userDir, 'logs'), { recursive: true });
  await fsp.mkdir(path.join(userDir, 'cache'), { recursive: true });
  logPath = path.join(userDir, 'logs/serwer.log');
  // Keep the previous run for diagnosing a startup failure, with bounded rotation.
  await fsp.rm(logPath + '.1', { force: true });
  await fsp.rename(logPath, logPath + '.1').catch(error => { if (error.code !== 'ENOENT') throw error; });
  log = fs.createWriteStream(logPath, { flags: 'w' });
  log.on('error', error => { log = undefined; void fail(error); });
  const platform = { linux: 'linux', darwin: 'mac', win32: 'win' }[process.platform];
  const resources = app.isPackaged ? process.resourcesPath : path.join(__dirname, 'staged');
  const pythonDir = app.isPackaged ? path.join(resources, 'python') : path.join(__dirname, 'runtime', `${platform}-${process.arch}`, 'python');
  const python = path.join(pythonDir, process.platform === 'win32' ? 'python.exe' : 'bin/python3');
  await fsp.access(python, fs.constants.X_OK);
  await fsp.access(path.join(resources, 'app/app.py'));
  const port = await freePort();
  origin = `http://127.0.0.1:${port}`;
  makeMenu();
  window = new BrowserWindow({ width: 1440, height: 1000, minWidth: 900, minHeight: 650,
    title: 'Laboratorium danych', backgroundColor: '#f7fafb',
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true, spellcheck: false }
  });
  window.webContents.setWindowOpenHandler(({ url }) => { openExternal(url); return { action: 'deny' }; });
  window.webContents.on('will-navigate', (event, url) => {
    if (new URL(url).origin !== origin) { event.preventDefault(); openExternal(url); }
  });
  window.webContents.session.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  window.webContents.session.on('will-download', (_event, item) => {
    item.setSaveDialogOptions({ title: 'Zapisz plik', defaultPath: path.join(app.getPath('downloads'), path.basename(item.getFilename())) });
  });
  window.webContents.on('render-process-gone', (_event, details) => { if (!stopping) void fail(new Error(`Okno aplikacji zostało zamknięte: ${details.reason}`)); });
  window.on('unresponsive', () => { if (!stopping) void fail(new Error('Okno aplikacji przestało odpowiadać.')); });
  await window.loadFile(path.join(__dirname, 'splash.html'));
  writeLog(`Starting Python on ${origin}; resources=${resources}`);
  server = spawn(python, ['-m', 'streamlit', 'run', path.join(resources, 'app/app.py'),
    '--server.address', '127.0.0.1', '--server.port', String(port), '--server.headless', 'true',
    '--browser.gatherUsageStats', 'false', '--server.fileWatcherType', 'none',
    // Bez przycisku „Deploy” i menu dewelopera Streamlit.
    '--client.toolbarMode', 'viewer'], {
    cwd: userDir, windowsHide: true, detached: process.platform !== 'win32',
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, LAB_DESKTOP: '1', LAB_USER_DIR: userDir,
      DATA_DIR: path.join(resources, 'dane'), LOG_DIR: path.join(userDir, 'logs'), CACHE_DIR: path.join(userDir, 'cache'),
      OLLAMA_BASE_URL: 'http://127.0.0.1:11434', ALLOW_CUSTOM_ENDPOINT: '1',
      PYTHONNOUSERSITE: '1', PYTHONDONTWRITEBYTECODE: '1', PYTHONUNBUFFERED: '1', PYTHONHOME: '', PYTHONPATH: '',
      NO_PROXY: [process.env.NO_PROXY, '127.0.0.1', 'localhost', '::1'].filter(Boolean).join(','),
      no_proxy: [process.env.no_proxy, '127.0.0.1', 'localhost', '::1'].filter(Boolean).join(',') }
  });
  server.stdout.on('data', chunk => log?.write(chunk));
  server.stderr.on('data', chunk => log?.write(chunk));
  server.on('error', error => { void fail(error); });
  server.on('exit', (code, signal) => { if (!stopping) void fail(new Error(`Serwer aplikacji zakończył pracę (kod ${code}, sygnał ${signal || 'brak'}).`)); });
  if (!server.pid) throw new Error('Nie udało się uruchomić Pythona.');
  writeLog(`Server PID: ${server.pid}`);
  // Independent monitor also cleans up after abrupt main-process death.
  const watchdog = spawn(python, [app.isPackaged ? path.join(resources, 'watchdog.py') : path.join(__dirname, 'scripts/watchdog.py'),
    String(process.pid), String(server.pid)], { windowsHide: true, detached: true, stdio: ['ignore', 'ignore', 'pipe'],
    env: { ...process.env, PYTHONNOUSERSITE: '1', PYTHONHOME: '', PYTHONPATH: '', PYTHONDONTWRITEBYTECODE: '1' } });
  watchdog.stderr.on('data', chunk => log?.write(chunk));
  watchdog.on('error', error => { if (!stopping) void fail(new Error(`Monitor procesu: ${error.message}`)); });
  watchdog.on('exit', code => { if (!stopping && code !== 0) void fail(new Error(`Monitor procesu zakończył pracę (kod ${code}).`)); });
  watchdog.unref();
  const deadline = Date.now() + 90000;
  while (Date.now() < deadline && !stopping) {
    if (await healthy(port)) {
      await window.loadURL(origin);
      if (smokePath) await captureSmoke();
      return;
    }
    await delay(250);
  }
  if (!stopping) throw new Error('Serwer nie uruchomił się w ciągu 90 sekund.');
}

if (!locked) {
  app.exit(smokePath ? 1 : 0);
} else {
  app.on('second-instance', () => { if (window) { if (window.isMinimized()) window.restore(); window.show(); window.focus(); } });
  app.on('before-quit', event => { event.preventDefault(); void finish(0); });
  app.on('window-all-closed', () => { void finish(0); });
  app.on('child-process-gone', (_event, details) => { if (!stopping && ['crashed', 'oom'].includes(details.reason)) void fail(new Error(`Proces okna: ${details.reason}`)); });
  process.on('uncaughtException', error => { void fail(error); });
  process.on('unhandledRejection', error => { void fail(error instanceof Error ? error : new Error(String(error))); });
  for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => { void finish(0); });
  app.whenReady().then(start).catch(fail);
}

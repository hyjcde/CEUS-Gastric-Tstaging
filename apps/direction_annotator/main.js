const { app, BrowserWindow, dialog, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');
const { fork } = require('child_process');

app.disableHardwareAcceleration();

const isProd = app.isPackaged || process.env.NODE_ENV === 'production';
const logPath = path.join(app.getPath('userData'), 'annotator.log');

function log(msg) {
  const ts = new Date().toISOString();
  const line = `[${ts}] ${msg}\n`;
  console.log(msg);
  try { fs.appendFileSync(logPath, line); } catch {}
}

log(`>>> 启动 | isPackaged: ${app.isPackaged} | isProd: ${isProd}`);

let mainWindow = null;
let selectedDataRoot = null;
let serverPort = 3099;
let serverProcess = null;

const configPath = path.join(app.getPath('userData'), 'config.json');
function loadConfig() {
  try { if (fs.existsSync(configPath)) return JSON.parse(fs.readFileSync(configPath, 'utf-8')); } catch {}
  return {};
}
function saveConfig(cfg) {
  try { fs.writeFileSync(configPath, JSON.stringify(cfg, null, 2)); } catch {}
}

ipcMain.handle('select-folder', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: '选择 dataset 文件夹或项目根目录',
    properties: ['openDirectory'],
  });
  if (result.canceled || !result.filePaths.length) return null;
  return result.filePaths[0];
});

ipcMain.handle('get-data-root', () => selectedDataRoot);
ipcMain.handle('get-server-port', () => serverPort);

ipcMain.handle('set-data-root', (_event, rootPath) => {
  selectedDataRoot = rootPath;
  process.env.DATA_ROOT = rootPath;
  saveConfig({ lastDataRoot: rootPath });
  log(`>>> 数据目录设定: ${rootPath}`);
  return true;
});

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1500,
    height: 950,
    title: '突破方向标注工具',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
    autoHideMenuBar: true,
    backgroundColor: '#010409',
  });

  const cfg = loadConfig();
  if (cfg.lastDataRoot && fs.existsSync(cfg.lastDataRoot)) {
    selectedDataRoot = cfg.lastDataRoot;
    process.env.DATA_ROOT = selectedDataRoot;
    log(`>>> 恢复上次数据目录: ${selectedDataRoot}`);
  }

  startServer();
}

async function startServer() {
  const loadingHtml = `<html><head><meta charset="UTF-8"></head>
    <body style="background:#010409;color:white;display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;font-family:system-ui;margin:0;">
      <div style="font-size:22px;font-weight:bold;margin-bottom:8px;">突破方向标注工具</div>
      <div style="font-size:13px;color:#94a3b8;">正在加载，请稍候...</div>
      <div style="margin-top:24px;width:200px;height:4px;background:#1e293b;border-radius:2px;overflow:hidden;">
        <div style="width:100%;height:100%;background:linear-gradient(90deg,#3b82f6,#60a5fa);animation:load 2s infinite ease-in-out;"></div>
      </div>
      <style>@keyframes load{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}</style>
    </body></html>`;
  mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(loadingHtml)}`);

  try {
    const appRoot = isProd ? app.getAppPath() : __dirname;
    log(`>>> App root: ${appRoot}`);

    // Use next directly (not standalone server.js) for both dev and prod
    const next = require('next');
    const { createServer } = require('http');
    const { parse } = require('url');

    const nextApp = next({ dev: !isProd, dir: appRoot });
    const handle = nextApp.getRequestHandler();
    await nextApp.prepare();
    log('>>> Next.js ready');

    const server = createServer((req, res) => {
      const parsedUrl = parse(req.url, true);
      handle(req, res, parsedUrl);
    });

    const tryListen = (p) => {
      server.listen(p, '127.0.0.1', () => {
        serverPort = p;
        log(`>>> 服务启动: http://127.0.0.1:${p}`);
        loadMainPage(p);
      });
    };

    server.on('error', (e) => {
      if (e.code === 'EADDRINUSE') {
        log(`>>> 端口 ${serverPort} 被占用，尝试 ${serverPort + 1}`);
        serverPort++;
        if (serverPort < 3120) tryListen(serverPort);
        else showError('无法找到可用端口 (3099-3119)');
      } else {
        showError(`服务启动失败: ${e.message}`);
      }
    });

    tryListen(serverPort);
  } catch (err) {
    log(`>>> 异常: ${err.stack}`);
    showError(`系统初始化失败: ${err.message}`);
  }
}

function loadMainPage(port, retries = 20) {
  mainWindow.loadURL(`http://127.0.0.1:${port}`).catch(() => {
    if (retries > 0) setTimeout(() => loadMainPage(port, retries - 1), 800);
    else showError(`无法连接到本地服务 (127.0.0.1:${port})`);
  });
}

function showError(msg) {
  const html = `<html><head><meta charset="UTF-8"></head>
    <body style="background:#0f172a;color:#f87171;padding:40px;font-family:system-ui;">
      <h1 style="font-size:18px;">启动失败</h1>
      <p style="color:white;font-size:13px;">${msg}</p>
      <p style="color:#94a3b8;font-size:11px;margin-top:16px;">日志文件: ${logPath}</p>
      <button onclick="location.reload()" style="margin-top:16px;padding:8px 16px;background:#3b82f6;color:white;border:none;border-radius:4px;cursor:pointer;">重试</button>
    </body></html>`;
  if (mainWindow) mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`);
}

app.whenReady().then(createWindow);
app.on('window-all-closed', () => {
  if (serverProcess) { try { serverProcess.kill(); } catch {} }
  if (process.platform !== 'darwin') app.quit();
});

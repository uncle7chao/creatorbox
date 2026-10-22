/**
 * 用系统 Chrome + CDP 抓小红书笔记页（验证未登录分享链接是否真能打开）
 *
 * 起因：用户给了条小红书链接问「没登录的视频不能解析吗」。
 * 纯 HTTP 抓到的页面里 noteData 是空的、notFoundPage=true，
 * 但那可能只是 SSR 不含数据（前端 XHR 异步加载）——
 * 必须用真浏览器看它到底渲染成什么。
 *
 * 参考技能：cdp-scrape-encrypted-pages（其踩坑表已记明
 *   「agent-browser 沙箱内挂死，改用裸 CDP 脚本」）
 */
const { spawn } = require('child_process');
const http = require('http');
const path = require('path');
const fs = require('fs');
const os = require('os');

const PORT = 9341;
const URL_ARG = process.argv[2];
const OUT = process.argv[3] || 'D:/WorkBuddyFILE/CreatorBox/.tmp_xhs';

const CHROME_CANDS = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
];

const sleep = ms => new Promise(r => setTimeout(r, ms));

function getJson(pathname) {
  return new Promise((resolve, reject) => {
    http.get({ host: '127.0.0.1', port: PORT, path: pathname, timeout: 4000 },
      res => {
        let b = '';
        res.on('data', d => (b += d));
        res.on('end', () => { try { resolve(JSON.parse(b)); } catch (e) { reject(e); } });
      }).on('error', reject);
  });
}

(async () => {
  const chrome = CHROME_CANDS.find(p => fs.existsSync(p));
  if (!chrome) { console.error('NO_CHROME'); process.exit(2); }
  console.log('CHROME=' + chrome);

  const profile = path.join(os.tmpdir(), 'cb_cdp_xhs_' + Date.now());
  const proc = spawn(chrome, [
    `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${profile}`,
    '--no-first-run', '--no-default-browser-check',
    '--disable-features=Translate,MediaRouter',
    '--window-size=1400,1000',
    'about:blank',
  ], { detached: true, stdio: 'ignore' });
  proc.unref();

  // 等 CDP 就绪
  let ready = false;
  for (let i = 0; i < 30; i++) {
    try { await getJson('/json/version'); ready = true; break; }
    catch (e) { await sleep(1000); }
  }
  if (!ready) { console.error('CDP_NOT_READY'); process.exit(3); }
  console.log('CDP_READY');

  const list = await getJson('/json/list');
  const target = list.find(t => t.type === 'page');
  if (!target) { console.error('NO_PAGE'); process.exit(4); }
  const wsUrl = target.webSocketDebuggerUrl;

  const WebSocket = require('ws');
  const ws = new WebSocket(wsUrl, { maxPayload: 512 * 1024 * 1024 });
  let msgId = 0;
  const pending = new Map();

  const send = (method, params) => new Promise((resolve) => {
    const id = ++msgId;
    pending.set(id, resolve);
    ws.send(JSON.stringify({ id, method, params: params || {} }));
  });

  ws.on('message', (raw) => {
    let m;
    try { m = JSON.parse(raw.toString()); } catch (e) { return; }
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); }
  });

  await new Promise((res, rej) => { ws.on('open', res); ws.on('error', rej); });

  await send('Page.enable');
  await send('Runtime.enable');
  await send('Network.enable');

  console.log('NAVIGATING...');
  await send('Page.navigate', { url: URL_ARG });

  // 小红书前端要时间解密/渲染；等久一点并轮询
  let bodyText = '';
  for (let i = 0; i < 8; i++) {
    await sleep(3000);
    const r = await send('Runtime.evaluate', {
      expression: 'document.body ? document.body.innerText : ""',
      returnByValue: true,
    });
    bodyText = (r && r.result && r.result.value) || '';
    console.log(`  T+${(i + 1) * 3}s  正文长度=${bodyText.length}`);
    if (bodyText.length > 200) break;
  }

  // 关键取证：页面里到底有没有视频/图片直链
  const probe = await send('Runtime.evaluate', {
    expression: `JSON.stringify({
      title: document.title,
      url: location.href,
      videos: [...document.querySelectorAll('video')].map(v => v.src || (v.querySelector('source')||{}).src).filter(Boolean),
      imgs: [...document.querySelectorAll('img')].map(i=>i.src).filter(s=>s.includes('sns-')).slice(0,5),
      hasLogin: /登录|扫码/.test(document.body.innerText.slice(0,3000)),
      hasNote: !!document.querySelector('#noteContainer, .note-container, .note-item'),
      bodyHead: document.body.innerText.slice(0, 600)
    })`,
    returnByValue: true,
  });

  fs.mkdirSync(OUT, { recursive: true });
  fs.writeFileSync(path.join(OUT, 'body.txt'), bodyText, 'utf8');
  const p = JSON.parse((probe && probe.result && probe.result.value) || '{}');
  fs.writeFileSync(path.join(OUT, 'probe.json'), JSON.stringify(p, null, 2), 'utf8');

  console.log('=== PROBE ===');
  console.log('title      :', p.title);
  console.log('hasLogin   :', p.hasLogin);
  console.log('hasNote    :', p.hasNote);
  console.log('videos     :', (p.videos || []).length, (p.videos || [])[0] || '');
  console.log('imgs(sns-) :', (p.imgs || []).length, (p.imgs || [])[0] || '');
  console.log('--- body 开头 ---');
  console.log((p.bodyHead || '').slice(0, 400));

  try { await send('Browser.close'); } catch (e) {}
  ws.close();
  process.exit(0);
})().catch(e => { console.error('ERR', e && e.message); process.exit(9); });

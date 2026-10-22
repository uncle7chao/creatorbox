/**
 * CDP 抓小红书笔记：找真实视频/图片直链
 *
 * 第一版发现：<video>.src 是 blob:（MSE 流式播放），真实地址在别处。
 * 这一版从三个地方取：
 *   ① window.__INITIAL_STATE__（前端解密后才有）
 *   ② window.__INITIAL_STATE__ 之外的全局变量 / performance 资源
 *   ③ Network 响应体里带 sns- 的 URL
 */
const { spawn } = require('child_process');
const http = require('http');
const path = require('path');
const fs = require('fs');
const os = require('os');

const PORT = 9342;
const URL_ARG = process.argv[2];
const OUT = process.argv[3] || 'D:/WorkBuddyFILE/CreatorBox/.tmp_xhs2';

const CHROME_CANDS = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
];
const sleep = ms => new Promise(r => setTimeout(r, ms));

function getJson(p) {
  return new Promise((resolve, reject) => {
    http.get({ host: '127.0.0.1', port: PORT, path: p, timeout: 4000 }, res => {
      let b = ''; res.on('data', d => (b += d));
      res.on('end', () => { try { resolve(JSON.parse(b)); } catch (e) { reject(e); } });
    }).on('error', reject);
  });
}

(async () => {
  const chrome = CHROME_CANDS.find(p => fs.existsSync(p));
  if (!chrome) { console.error('NO_CHROME'); process.exit(2); }
  const profile = path.join(os.tmpdir(), 'cb_cdp_xhs2_' + Date.now());
  const proc = spawn(chrome, [
    `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
    '--no-first-run', '--no-default-browser-check',
    '--autoplay-policy=no-user-gesture-required',
    '--window-size=1400,1000', 'about:blank',
  ], { detached: true, stdio: 'ignore' });
  proc.unref();

  let ready = false;
  for (let i = 0; i < 30; i++) {
    try { await getJson('/json/version'); ready = true; break; } catch (e) { await sleep(1000); }
  }
  if (!ready) { console.error('CDP_NOT_READY'); process.exit(3); }

  const list = await getJson('/json/list');
  const target = list.find(t => t.type === 'page');
  const WebSocket = require('ws');
  const ws = new WebSocket(target.webSocketDebuggerUrl,
    { maxPayload: 512 * 1024 * 1024 });
  let msgId = 0; const pending = new Map();
  const netUrls = new Set();

  const send = (method, params) => new Promise((resolve) => {
    const id = ++msgId; pending.set(id, resolve);
    ws.send(JSON.stringify({ id, method, params: params || {} }));
  });

  ws.on('message', (raw) => {
    let m; try { m = JSON.parse(raw.toString()); } catch (e) { return; }
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); return; }
    // 收集网络请求 URL
    if (m.method === 'Network.requestWillBeSent') {
      const u = m.params && m.params.request && m.params.request.url;
      if (u && (u.includes('sns-') || u.includes('.mp4') || u.includes('xhscdn'))) netUrls.add(u);
    }
  });

  await new Promise((res, rej) => { ws.on('open', res); ws.on('error', rej); });
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Network.enable');
  await send('Page.navigate', { url: URL_ARG });

  for (let i = 0; i < 10; i++) {
    await sleep(3000);
    const r = await send('Runtime.evaluate', {
      expression: 'document.title', returnByValue: true });
    const t = (r && r.result && r.result.value) || '';
    console.log(`  T+${(i + 1) * 3}s  title="${t}"  netUrls=${netUrls.size}`);
    if (t && !t.includes('小红书 -') && i >= 3) break;
  }

  const probe = await send('Runtime.evaluate', {
    expression: `(() => {
      const out = { title: document.title, stateFound: false, note: null, urls: [] };
      // ① __INITIAL_STATE__
      try {
        const raw = window.__INITIAL_STATE__;
        if (raw) {
          out.stateFound = true;
          const s = typeof raw === 'string' ? raw : JSON.stringify(raw);
          // 抓所有含 sns- 的 URL
          const m = s.match(/https[^"\\\\\\s]*sns-[^"\\\\\\s]{10,200}/g) || [];
          out.urls = [...new Set(m)].slice(0, 40);
          // 找 noteDetailMap / noteData
          try {
            const st = typeof raw === 'string' ? null : raw;
            if (st) {
              const ndm = st.note && st.note.noteDetailMap;
              if (ndm) {
                for (const k of Object.keys(ndm)) {
                  const n = ndm[k] && ndm[k].note;
                  if (n) { out.note = { id: k, title: n.title, type: n.type,
                    desc: (n.desc||'').slice(0,200),
                    imgs: (n.imageList||[]).map(i=>i.url).filter(Boolean).slice(0,10),
                    videoKeys: n.video ? Object.keys(n.video.media||{}) : [],
                    hasVideo: !!n.video }; break; }
                }
              }
            }
          } catch(e) { out.noteErr = String(e).slice(0,120); }
        }
      } catch(e) { out.stateErr = String(e).slice(0,120); }
      // ② 全局变量里找 media / originVideoKey
      try {
        const g = window;
        for (const k of Object.keys(g)) {
          if (/note|media|video|state/i.test(k) && typeof g[k] === 'object' && g[k]) {
            const s = JSON.stringify(g[k]);
            if (s && s.length > 200 && s.length < 3000000) {
              const m = s.match(/https[^"\\\\\\s]*sns-[^"\\\\\\s]{10,200}/g) || [];
              if (m.length) out.urls = [...new Set(out.urls.concat(m))].slice(0,60);
            }
          }
        }
      } catch(e) {}
      return JSON.stringify(out);
    })()`,
    returnByValue: true,
  });

  const p = JSON.parse((probe && probe.result && probe.result.value) || '{}');
  p.netUrls = [...netUrls].slice(0, 60);
  fs.mkdirSync(OUT, { recursive: true });
  fs.writeFileSync(path.join(OUT, 'probe.json'), JSON.stringify(p, null, 2), 'utf8');

  console.log('\n=== 状态 ===');
  console.log('title      :', p.title);
  console.log('stateFound :', p.stateFound, p.stateErr || '');
  console.log('note       :', p.note ? JSON.stringify(p.note).slice(0, 300) : '(未取到)');
  console.log('\n=== state/全局里的 sns 直链 ===');
  (p.urls || []).slice(0, 12).forEach(u => console.log('  ', u.slice(0, 110)));
  console.log('\n=== 网络请求里的候选 ===');
  (p.netUrls || []).filter(u => u.includes('.mp4') || u.includes('sns-video') || u.includes('stream'))
    .slice(0, 12).forEach(u => console.log('  ', u.slice(0, 110)));

  try { await send('Browser.close'); } catch (e) {}
  ws.close(); process.exit(0);
})().catch(e => { console.error('ERR', e && e.message); process.exit(9); });

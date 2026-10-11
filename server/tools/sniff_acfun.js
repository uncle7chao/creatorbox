/**
 * AcFun 榜单页 XHR 抓取：无头浏览器加载页面，拦截全部网络响应，
 * 找出返回榜单数据的请求（含视频标题/acId 的 JSON）
 */
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ userAgent:
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36' });

  const hits = [];
  page.on('response', async (resp) => {
    try {
      const url = resp.url();
      if (!/acfun\.cn/.test(url) || /\.(js|css|png|jpg|gif|webp|ico|mp4)/.test(url)) return;
      const ct = (resp.headers()['content-type'] || '');
      if (!/json/i.test(ct)) return;
      const body = await resp.text();
      // 榜单数据特征：含视频标题+acId 或 rankList
      if (body.length > 500 && (body.includes('"acId"') || body.includes('acid') ||
          body.includes('ac') + /"title"/.test(body) || /rank/i.test(url))) {
        hits.push({ url, size: body.length, head: body.slice(0, 300) });
      }
    } catch (e) { /* 忽略流式读取错误 */ }
  });

  await page.goto('https://www.acfun.cn/rank/list/?cid=-1&pcid=-1&range=DAY',
                  { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(8000);           // 等 XHR 全部发出

  // 页面渲染出来的榜单条目（真实 DOM 验证）
  const domItems = await page.evaluate(() => {
    const out = [];
    document.querySelectorAll('a[href*="/v/ac"]').forEach(a => {
      out.push({ href: a.getAttribute('href'), text: (a.textContent || '').trim().slice(0, 30) });
    });
    return out;
  });
  console.log('=== DOM 中渲染的榜单视频链接:', domItems.length);
  domItems.slice(0, 6).forEach(d => console.log('  ', d.href, '|', d.text));

  console.log('\n=== XHR 命中（含数据特征的 JSON 响应）:', hits.length);
  hits.slice(0, 8).forEach(h => {
    console.log('URL:', h.url.slice(0, 130));
    console.log('  size:', h.size, '| head:', h.head.slice(0, 200).replace(/\n/g, ' '));
  });

  await browser.close();
})();

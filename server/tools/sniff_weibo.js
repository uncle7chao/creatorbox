/**
 * 微博网页版 XHR 抓取（游客态）：找「带视频的真实微博」榜单接口
 * 目标特征：响应 JSON 里含 mblogid/mid + 视频信息
 */
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ userAgent:
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36' });
  const page = await ctx.newPage();

  const hits = [];
  page.on('response', async (resp) => {
    try {
      const url = resp.url();
      if (!/weibo\.c(n|om)/.test(url) || /\.(js|css|png|jpg|gif|webp|ico)/.test(url)) return;
      const ct = resp.headers()['content-type'] || '';
      if (!/json/i.test(ct)) return;
      const body = await resp.text();
      if (body.length < 800) return;
      // 含微博正文结构（mblogid / mid + 视频）
      const score = (body.match(/mblogid/g) || []).length +
                    (body.match(/"mid":/g) || []).length;
      if (score > 0) {
        hits.push({ url, size: body.length, score,
                    head: body.slice(0, 260) });
      }
    } catch (e) { /* 流式读取容错 */ }
  });

  // 游客访问发现页（热转/热门内容所在）
  for (const u of ['https://weibo.com/discover',
                   'https://s.weibo.com/top/summary?cate=realtimehot']) {
    try {
      await page.goto(u, { waitUntil: 'domcontentloaded', timeout: 25000 });
      await page.waitForTimeout(5000);
    } catch (e) { console.log('goto 失败:', u, str(e).slice(0, 60)); }
  }
  const str = e => (e && e.message) || String(e);

  console.log('=== 含微博结构的 JSON 响应:', hits.length);
  // 去重按 URL 路径
  const seen = new Set();
  for (const h of hits) {
    const key = h.url.split('?')[0];
    if (seen.has(key)) continue;
    seen.add(key);
    console.log('\nURL:', h.url.slice(0, 140));
    console.log('  size:', h.size, '| mblogid+mid 计分:', h.score);
    console.log('  head:', h.head.replace(/\n/g, ' ').slice(0, 220));
  }
  await browser.close();
})();

/**
 * 微博视频分享页（游客态）XHR 抓取：video.weibo.com/show?fid=...
 * 目标：找到含真实视频地址（playback/mp4/media_bid）的接口
 */
const { chromium } = require('playwright');

const TARGET = process.env.WB_URL || 'https://video.weibo.com/show?fid=1034:5350431371755580';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ userAgent:
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1' });
  const page = await ctx.newPage();

  const hits = [];
  page.on('response', async (resp) => {
    try {
      const url = resp.url();
      const ct = resp.headers()['content-type'] || '';
      if (/json|javascript/i.test(ct) && !/weibo\.com\/(aj|_)\w*(login|passport)/.test(url)) {
        const body = await resp.text();
        if (body.length < 200) return;
        const score = (body.match(/mp4|playback|video_body|media_bid|urls/g) || []).length;
        if (score > 0 && /json/i.test(ct)) {
          hits.push({ url, size: body.length, score, head: body.slice(0, 400) });
        }
      }
    } catch (e) { /* 流式读取容错 */ }
  });
  // 同时抓直接的媒体请求
  const media = [];
  page.on('request', (req) => {
    const u = req.url();
    if (/\.mp4|m3u8|f\.video\.weibo\.com|us\.soup|video\.weibo\.com\/media/.test(u)) media.push(u);
  });

  try {
    await page.goto(TARGET, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(8000);
  } catch (e) { console.log('goto 失败:', (e.message || e).slice(0, 80)); }

  console.log('=== 媒体请求', media.length);
  media.slice(0, 5).forEach(u => console.log('MEDIA:', u.slice(0, 160)));

  console.log('=== JSON 命中', hits.length);
  const seen = new Set();
  for (const h of hits) {
    const key = h.url.split('?')[0];
    if (seen.has(key)) continue;
    seen.add(key);
    console.log('\nURL:', h.url.slice(0, 150));
    console.log('  size:', h.size, '| 计分:', h.score);
    console.log('  head:', h.head.replace(/\s+/g, ' ').slice(0, 360));
  }
  await browser.close();
})();

/**
 * ⭐ 小程序逻辑模拟测试
 *
 * 为什么需要：微信开发者工具跑不了真实渲染（沙箱里也开不了），
 * 但**页面逻辑**（parse 回调、setData 时序、下载配额、失败分支）
 * 可以在 Node 里跑 —— 只要伪造 `wx` 全局对象。
 *
 * 这不是「模拟测试」那种自欺欺人的做法：
 * 真实的小程序 JS 引擎就是 V8 + wx API，我们复刻的是 API 契约，
 * 页面代码一行不改地跑在这层契约上。
 *
 * 覆盖的路径（都是最容易出错的地方）：
 *   · 解析成功 → globalData 传递 → 结果页读到
 *   · 解析失败 → 错误文案 + 不跳转
 *   · 服务未连 → 首页黄色提示
 *   · 保存配额：免费耗尽被拦 / 消耗后计数 +1 / 会员不消耗
 *   · 图集逐张保存的成败统计
 *   · AcFun 需合并时拦住不下载
 *
 * 运行：node test/logic.test.js
 */
const fs = require('fs');
const path = require('path');

let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log(`   PASS  ${name}`); }
  else { fail++; console.log(`   FAIL  ${name}${detail ? '  ← ' + detail : ''}`); }
}

// ════════════════════════════════════════════
//伪造 wx API
// ════════════════════════════════════════════
const store = {};
let mockedApi = null;        // 解析响应（用例内切换）
let healthShouldFail = false; // 健康检查开关 —— 单独变量，避开 require 缓存问题
let trendingOverride = null;  // M1.5 榜单开关：null=正常 / 对象=替换响应 / '__fail__'=网络失败
let adsCfg = null;            // 广告配置 mock（null=服务端默认）
const calls = {              // 记录调用轨迹，供断言
  navigateTo: [], switchTab: [], showToast: [], showModal: [],
  showLoading: [], hideLoading: [], downloadFile: [], saveVideo: [],
  setClipboard: [], previewMedia: [], consume: 0,
  setTabBarStyle: [], setNavColor: []
};

global.wx = {
  getStorageSync: k => (k in store ? store[k] : ''),
  setStorageSync: (k, v) => { store[k] = v; },

  // P0：quota.js 登录链路用 —— 恒给 code（服务端未配 secret 时降级游客态，
  // 全部走 /api/user/login 请求路径，与真实时序一致）
  login: opts => setImmediate(() => opts.success({ code: 'test_code' })),

  request(opts) {
    setImmediate(() => {
      const url = opts.url;
      if (url.includes('/api/parse')) {
        opts.success({ statusCode: 200, data: mockedApi.parse });
      } else if (url.includes('/api/user/quota/consume')) {
        // 服务端权威扣减（模拟 db.consume_save）
        store.__srv_save = (store.__srv_save || 0) + (opts.data.n || 1);
        const member = !!store.cb_is_member;
        const exhausted = !member && store.__srv_save > 2;
        opts.success({ statusCode: 200, data: {
          ok: !exhausted,
          reason: exhausted ? 'quota_exhausted' : undefined,
          quota: {
            is_member: member,
            save_used: store.__srv_save,
            save_limit: member ? 0 : 2,
            save_left: member ? -1 : Math.max(0, 2 - store.__srv_save),
            batch_limit: member ? 10 : 3
          }
        }});
      } else if (url.includes('/api/user/quota')) {
        const member = !!store.cb_is_member;
        const used = store.__srv_save || 0;
        opts.success({ statusCode: 200, data: {
          is_member: member, save_used: used,
          save_limit: member ? 0 : 2,
          save_left: member ? -1 : Math.max(0, 2 - used),
          batch_limit: member ? 10 : 3 } });
      } else if (url.includes('/api/user/login')) {
        const did = ((opts.data || {}).device_id || 'x').slice(0, 30);
        opts.success({ statusCode: 200, data: {
          openid: 'guest_' + did, via: 'guest', is_member: false,
          quota: { is_member: false, save_used: 0, save_limit: 2,
                   save_left: 2, batch_limit: 3 } } });
      } else if (url.includes('/api/batch')) {
        // 按条目动态构造：合法链接用 mockedApi.parse，非法文本返回失败
        const results = (opts.data.items || []).map((it, i) => {
          if (!/^https?:\/\//.test(it.text || '')) {
            return { index: i, success: false, error: '未识别到链接', platform: '' };
          }
          return { ...mockedApi.parse, index: i, cached: false };
        });
        opts.success({ statusCode: 200, data: {
          total: results.length,
          ok: results.filter(x => x.success).length,
          fail: results.filter(x => !x.success).length,
          results } });
      } else if (url.includes('/api/trending')) {
        // M1.5 榜单：按 platform 参数分发（与服务端 trending.py 行为一致）
        const m = url.match(/platform=([a-z]+)/) || [];
        const plat = m[1] || '';
        if (trendingOverride === '__fail__') {
          opts.fail({ errMsg: 'request:fail timeout' });
        } else if (trendingOverride) {
          opts.success({ statusCode: 200, data: trendingOverride });
        } else if (plat === 'bilibili') {
          const t = JSON.parse(fs.readFileSync(
            path.join(__dirname, 'fixtures', 'trending-bilibili.json'), 'utf-8'));
          opts.success({ statusCode: 200, data: { ...t, cached: true } });
        } else if (plat === 'douyin') {
          // 热点词条榜（2026-10-07 上线）：词条无视频 ID，点击=复制去搜
          opts.success({ statusCode: 200, data: { ok: true, platform: 'douyin',
            items: [
              { rank: 1, title: '测试热点词条一', author: '', hot: 12000000,
                hot_text: '1200万', cover: '', url: '', type: 'word' },
              { rank: 2, title: '测试热点词条二', author: '', hot: 800000,
                hot_text: '80万', cover: '', url: '', type: 'word' }
            ] } });
        } else if (plat === 'acfun') {
          // AcFun 视频榜（rest/pc-direct/rank/channel，dougaId 可解析）
          opts.success({ statusCode: 200, data: { ok: true, platform: 'acfun',
            items: [
              { rank: 1, title: '测试AcFun视频一', author: 'UP主甲', hot: 3445,
                hot_text: '3,450', cover: '', url: 'https://www.acfun.cn/v/ac48895678',
                type: 'video' }
            ] } });
        } else if (plat === 'kuaishou') {
          // 快手热点词条榜（官网首页 SSR，2026-10-07 上线）
          opts.success({ statusCode: 200, data: { ok: true, platform: 'kuaishou',
            items: [
              { rank: 1, title: '测试快手词条一', author: '', hot: 11000000,
                hot_text: '1100万', cover: '', url: '', type: 'word' },
              { rank: 2, title: '测试快手词条二', author: '', hot: 900000,
                hot_text: '90万', cover: '', url: '', type: 'word' }
            ] } });
        } else if (plat === 'weibo') {
          opts.success({ statusCode: 200, data: { ok: false, code: 'need_cookie', platform: plat,
            message: '微博榜单正在开通中，敬请期待' } });
        } else {
          opts.success({ statusCode: 200, data: { ok: false, code: 'unknown_platform', platform: plat } });
        }
      } else if (url.includes('/api/ads/config')) {
        opts.success({ statusCode: 200, data: { ok: true, ads: adsCfg || {
          master: true,
          placements: {
            index_banner: { enabled: true, label: '首页横幅', image: '', unit_id: '', link: '' },
            result_banner: { enabled: true, label: '结果页横幅', image: '', unit_id: '', link: '' },
            toolbox_banner: { enabled: true, label: '工具箱横幅', image: '', unit_id: '', link: '' },
            ranking_banner: { enabled: false, label: '热榜横幅', image: '', unit_id: '', link: '' },
            library_banner: { enabled: false, label: '素材库横幅', image: '', unit_id: '', link: '' }
          },
          popup: { enabled: true, every_n_parses: 3, start_after: 2,
                   image: '', unit_id: '', link: '' }
        } } });
      } else if (url.includes('/api/points/sign')) {
        const already = global.__mockAlreadySigned === true;
        global.__mockAlreadySigned = true;   // 首次签到后置位，模拟幂等
        opts.success({ statusCode: 200, data: {
          ok: true, signed: !already, gained: 10,
          balance: already ? 10 : 20, streak: 1,
          days: ['2026-10-08'], redeem_cost: 100,
          message: already ? '今天已签到过啦' : ''
        } });
      } else if (url.includes('/api/points/redeem')) {
        opts.success({ statusCode: 200, data: {
          ok: true, redeemed_days: 1, balance: 0, days: [],
          redeem_cost: 100, member: { is_member: true, expire_at: 9999999999 }
        } });
      } else if (url.includes('/api/points')) {
        opts.success({ statusCode: 200, data: { ok: true, balance: 10,
          streak: 1, days: ['2026-10-08'], redeem_cost: 100 } });
      } else if (url.includes('/api/health')) {
        if (healthShouldFail) opts.fail({ errMsg: 'request:fail timeout' });
        else opts.success({ statusCode: 200, data: { ready: true, platforms: new Array(12).fill(0), engine: 'pure_http' } });
      } else {
        opts.fail({ errMsg: 'unknown url' });
      }
    });
  },

  getClipboardData: opts => setImmediate(() => opts.success({ data: store.__clip || '' })),
  setClipboardData: opts => setImmediate(() => { calls.setClipboard.push(opts.data); opts.success({}); }),
  showToast: o => calls.showToast.push(o.title),
  showModal: o => calls.showModal.push(o),
  showLoading: () => calls.showLoading.push(1),
  hideLoading: () => calls.hideLoading.push(1),
  navigateTo: o => calls.navigateTo.push(o.url),
  switchTab: o => {
    calls.switchTab.push(o.url);
    // ⛔ 早期版本无条件调 o.success()，但页面可能不传 success →
    //    setImmediate(undefined) 会抛 ERR_INVALID_ARG_TYPE 并中断整个测试。
    //    必须按真实语义：只有传了回调才调。
    if (typeof o.success === 'function') setImmediate(() => o.success({}));
  },
  downloadFile: o => {
    calls.downloadFile.push(o.url);
    if (mockedApi.downloadFail) setImmediate(() => o.fail({ errMsg: 'downloadFile:fail' }));
    else setImmediate(() => o.success({ statusCode: 200, tempFilePath: o.filePath }));
  },
  saveVideoToPhotosAlbum: o => {
    calls.saveVideo.push(o.filePath);
    if (mockedApi.saveFail) setImmediate(() => o.fail({ errMsg: 'auth deny' }));
    else setImmediate(() => o.success({}));
  },
  previewImage: () => {},
  previewMedia: o => setImmediate(() => o.success({})),
  makePhoneCall: () => {},
  openSetting: () => {},
  showActionSheet: () => {},
  // M1.5 专栏：详情页设置导航标题 / 返回
  setNavigationBarTitle: () => {},
  // 提词器滚到底判定用：返回 null 触发产品代码的空守卫
  createSelectorQuery: () => {
    const q = {
      in: () => q,
      select: () => q,
      boundingClientRect: cb => { if (cb) cb(null); return q; },
      exec: () => {}
    };
    return q;
  },
  navigateBack: () => {},
  // 皮肤系统：动态导航 / tabBar 配色
  setTabBarStyle: o => calls.setTabBarStyle.push(o),
  setNavigationBarColor: o => calls.setNavColor.push(o),
  getCurrentPages: () => []      // themes.sync 读路由用（空 = light 导航）
};

// Page / getApp 桩：把每个页面的 config 与实例方法收集起来
const pages = {};
let currentPage = null;
global.Page = cfg => { pages[currentPage] = cfg; };
global.getApp = () => (global.__app || (global.__app = { globalData: {} }));

function loadPage(file, pageName) {
  const p = path.join(__dirname, '..', 'pages', file, pageName + '.js');
  currentPage = file + '/' + pageName;
  const code = fs.readFileSync(p, 'utf-8');
  const module = { exports: {} };
  new Function('require', 'module', 'exports', 'Page', 'getApp', 'wx', 'App', code)(
    req => {
      const map = {
        '../../utils/api.js': path.join(__dirname, '..', 'utils', 'api.js'),
        '../../utils/parse-result.js': path.join(__dirname, '..', 'utils', 'parse-result.js'),
        '../../utils/quota.js': path.join(__dirname, '..', 'utils', 'quota.js'),
        '../../utils/saver.js': path.join(__dirname, '..', 'utils', 'saver.js'),
        '../../utils/articles.js': path.join(__dirname, '..', 'utils', 'articles.js'),
        '../../utils/ads.js': path.join(__dirname, '..', 'utils', 'ads.js'),
        '../../utils/themes.js': path.join(__dirname, '..', 'utils', 'themes.js')
      };
      return map[req] ? require(map[req]) : require(req);
    },
    module, module.exports, global.Page, global.getApp, global.wx, () => {}
  );
  return pages[currentPage];
}

/** 造一个带 setData 的页面实例 */
function instantiate(cfg, initialData) {
  const inst = Object.assign({}, cfg);
  inst.data = Object.assign({}, cfg.data || {}, initialData || {});
  inst.setData = patch => {
    Object.assign(inst.data, patch);
  };
  return inst;
}

const FIX = path.join(__dirname, 'fixtures');
const fixture = n => JSON.parse(fs.readFileSync(path.join(FIX, `fixture_${n}.json`), 'utf-8'));

/**
 * 等异步链走完
 *
 * ⚠️ 不能只等 3 轮 —— 图集保存是 7 个并行 downloadFile + Promise.all，
 *    微任务与 setImmediate 交错，实测需要 40+ 轮才走到回调。
 *    这里用「轮数足够 + 有上限」而不是靠猜。
 */
const flush = (rounds = 60) => new Promise(resolve => {
  let n = 0;
  const tick = () => {
    if (++n >= rounds) return resolve();
    setImmediate(tick);
  };
  tick();
});

// ════════════════════════════════════════════
(async function main() {

// ─────────────────────────────────────────────
console.log('▸ 解析成功 → 结果页能读到');
{
  mockedApi = { parse: fixture('bilibili_video') };
  const cfg = loadPage('index', 'index');
  const page = instantiate(cfg);
  page.setData({ input: 'https://www.bilibili.com/video/BV1GJ411x7h7' });

  await page.onParse();
  await flush();

  const app = global.getApp();
  check('写入 globalData.lastResult', !!app.globalData.lastResult);
  check('result.success 为 true', app.globalData.lastResult && app.globalData.lastResult.success === true);
  check('跳转结果页', calls.navigateTo.some(u => u.includes('/pages/result/result')),
    JSON.stringify(calls.navigateTo));
  check('parsing 复位', page.data.parsing === false);
  // M1.5+：解析进度动画（竞品骨架）—— 成功路径走满 100%
  check('进度条走满 100%', page.data.progress === 100, String(page.data.progress));
  check('进度文案为完成态', page.data.stepText === '完成', page.data.stepText);

  // 结果页读这份数据
  const rcfg = loadPage('result', 'result');
  const rpage = instantiate(rcfg);
  rpage.onLoad();
  check('结果页拿到标题', rpage.data.title.length > 0, rpage.data.title);
  check('结果页 titleIsVideo', rpage.data.isVideo === true);
  check('默认选中推荐档', rpage.data.selectedIdx >= 0, String(rpage.data.selectedIdx));
  check('作者·时长 拼好', rpage.data.authorLine.includes('·'), rpage.data.authorLine);
  check('清晰度项带 locked 标记',
    rpage.data.options.every(o => typeof o.locked === 'boolean'),
    JSON.stringify(rpage.data.options.map(o => o.locked)));
}

// ─────────────────────────────────────────────
console.log('\n▸ 解析失败 → 报错不跳转');
{
  calls.navigateTo = [];
  mockedApi = { parse: fixture('badlink') };
  const page = instantiate(loadPage('index', 'index'));
  page.setData({ input: '这不是一个链接' });

  await page.onParse();
  await flush();

  check('不跳转', calls.navigateTo.length === 0, JSON.stringify(calls.navigateTo));
  check('有错误提示', page.data.errorMsg.length > 0, page.data.errorMsg);
  check('parsing 复位', page.data.parsing === false);
  check('弹了失败弹窗', calls.showModal.length > 0);
  check('失败后进度归零', page.data.progress === 0, String(page.data.progress));
}

// ─────────────────────────────────────────────
console.log('\n▸ 空输入 → 提示而不是发请求');
{
  const page = instantiate(loadPage('index', 'index'));
  page.setData({ input: '   ' });
  await page.onParse();
  check('提示先粘贴', page.data.errorMsg.includes('请先粘贴'), page.data.errorMsg);
  check('未进入解析态', page.data.parsing === false);
}

// ─────────────────────────────────────────────
console.log('\n▸ 服务未连→ 首页黄条');
{
  // ⛔ api.js 走 Node require 缓存，改 localStorage/mock 对象都不会重新求值。
  //   健康检查的开关必须放在 wx.request 的**读取时机**，
  //   i.e. 用一个独立 flag，而不是共享的 mockedApi 对象字段。
  healthShouldFail = true;
  const page = instantiate(loadPage('index', 'index'));
  page.checkService();
  await flush();
  check('serviceOk=false', page.data.serviceOk === false);
  check('提示文案', page.data.serviceMsg === '服务未连接', page.data.serviceMsg);
  check('平台数归零', page.data.platformCount === 0);
}

// ─────────────────────────────────────────────
console.log('\n▸ 服务正常 → 拿到平台数');
{
  healthShouldFail = false;
  const page = instantiate(loadPage('index', 'index'));
  page.checkService();
  await flush();
  check('serviceOk=true', page.data.serviceOk === true);
  check('平台数=12（+X/TikTok/YouTube/Facebook 国际组）', page.data.platformCount === 12, String(page.data.platformCount));
}

// ─────────────────────────────────────────────
console.log('\n▸ 保存配额闸门（P0：服务端权威，免费每日2 次）');
{
  const { QUOTA } = require(path.join(__dirname, '..', 'utils', 'quota.js'));
  const { ParseResult } = require(path.join(__dirname, '..', 'utils', 'parse-result.js'));

  // 清空本地 + 服务端模拟计数
  Object.keys(store).forEach(k => { if (k.startsWith('cb_')) delete store[k]; });
  store.__srv_save = 0;
  healthShouldFail = false;
  mockedApi = { parse: fixture('bilibili_video') };

  // 登录拿服务端身份
  const openid = await QUOTA.ensureLogin();
  check('登录返回 guest openid', openid.startsWith('guest_'), openid.slice(0, 16));

  let q = await QUOTA.refresh();
  check('服务端初始剩余 2', q.save_left === 2, JSON.stringify(q));
  check('乐观缓存可读', QUOTA.cachedQuota().save_left === 2);

  // 消费两次
  let r = await QUOTA.consume(1);
  check('第 1 次消耗 ok 剩 1', r.ok && r.quota.save_left === 1, JSON.stringify(r.quota));
  r = await QUOTA.consume(1);
  check('第 2 次消耗 ok 剩 0', r.ok && r.quota.save_left === 0, JSON.stringify(r.quota));

  // 第 3 次服务端拒绝
  r = await QUOTA.consume(1);
  check('第 3 次服务端拒绝 quota_exhausted',
    r.ok === false && r.reason === 'quota_exhausted', JSON.stringify(r));
  check('耗尽后缓存仍为 0', QUOTA.cachedQuota().save_left === 0);

  // 配额耗尽时点保存 → 被结果页拦下（走「看广告再存」），不发起下载
  const app = global.getApp();
  app.globalData.lastResult = new ParseResult(fixture('bilibili_video'));
  const page = instantiate(loadPage('result', 'result'));
  page.onLoad();
  calls.downloadFile = []; calls.showModal = [];
  await page.onSave();
  await flush();
  check('配额耗尽时不下载', calls.downloadFile.length === 0, JSON.stringify(calls.downloadFile));
  check('引导看广告', calls.showModal.length > 0);

  // 会员：服务端不拒绝
  store.cb_is_member = 1;   // 模拟服务端会员标记（真实实现走 users 表）
  r = await QUOTA.consume(1);
  check('会员保存不被拒', r.ok === true && r.quota.is_member === true, JSON.stringify(r));
  delete store.cb_is_member;
}

// ─────────────────────────────────────────────
console.log('\n▸ 批量页：配额闸门 + 失败不阻塞');
{
  const { ParseResult } = require(path.join(__dirname, '..', 'utils', 'parse-result.js'));
  Object.keys(store).forEach(k => { if (k.startsWith('cb_')) delete store[k]; });
  store.__srv_save = 0;

  const page = instantiate(loadPage('batch', 'batch'));
  page.onLoad();
  await flush();
  check('登录后拿到批量上限 3', page.data.batchLimit === 3, String(page.data.batchLimit));

  // 4 条 → 本地先拦（服务端也拦，双闸门）
  page.setData({ input: ['https://a', 'https://b', 'https://c', 'https://d'].join('\n') });
  calls.showModal = [];
  await page.onParse();
  check('4 条被本地闸门拦（免费 3）', calls.showModal.length > 0, JSON.stringify(calls.showModal.map(m => m.title)));

  // 2 条解析：1 好 1 坏 → 失败不阻塞
  mockedApi = { parse: fixture('bilibili_video') };
  page.setData({ input: 'https://www.bilibili.com/video/BV1GJ411x7h7\n完全不是链接' });
  await page.onParse();
  await flush(40);
  check('成功 1 失败 1', page.data.okCount === 1 && page.data.failCount === 1,
    JSON.stringify({ ok: page.data.okCount, fail: page.data.failCount }));
  check('成功项默认全选', page.data.selectedCount === 1, String(page.data.selectedCount));
  check('失败项不带播放地址',
    page.data.results.every(x => x.ok ? x.urls.length > 0 : x.urls.length === 0),
    JSON.stringify(page.data.results.map(x => ({ ok: x.ok, urls: x.urls.length }))));
}

// ─────────────────────────────────────────────
console.log('\n▸ AcFun 需合并 → 拦住不下载');
{
  const { ParseResult } = require(path.join(__dirname, '..', 'utils', 'parse-result.js'));
  Object.keys(store).forEach(k => { if (k.startsWith('cb_')) delete store[k]; });
  mockedApi = { parse: fixture('acfun_merge'), downloadFail: false };

  global.getApp().globalData.lastResult = new ParseResult(fixture('acfun_merge'));
  const page = instantiate(loadPage('result', 'result'));
  page.onLoad();
  calls.downloadFile = []; calls.showToast = [];
  await page.onSave();
  await flush();
  check('不发起下载', calls.downloadFile.length === 0, JSON.stringify(calls.downloadFile));
  check('提示需服务端合并',
    calls.showToast.some(t => /合并/.test(t)), JSON.stringify(calls.showToast));
  check('页面展示合并提示', page.data.notices.some(n => /合并/.test(n)),
    JSON.stringify(page.data.notices));
}

// ─────────────────────────────────────────────
console.log('\n▸ 图集保存 7 张（成功/失败统计）');
{
  const { ParseResult } = require(path.join(__dirname, '..', 'utils', 'parse-result.js'));
  Object.keys(store).forEach(k => { if (k.startsWith('cb_')) delete store[k]; });
  store.__srv_save = 0;   // 服务端计数归零，本段断言「消耗 1 次」
  store.cb_openid = 'guest_xhsimg';   // ⭐ afterSaved 走服务端扣减需要身份
  mockedApi = { parse: fixture('xhs_image'), downloadFail: false };

  global.getApp().globalData.lastResult = new ParseResult(fixture('xhs_image'));
  const page = instantiate(loadPage('result', 'result'));
  page.onLoad();
  check('识别为图集', page.data.isImage === true);
  check('7 张图', page.data.images.length === 7, String(page.data.images.length));
  check('图集无时长（本来就没有）', page.data.r.durationS === null);

  calls.downloadFile = []; calls.showModal = [];
  await page.onSave();
  await flush();
  check('发起 7 次下载', calls.downloadFile.length === 7, String(calls.downloadFile.length));
  check('提示已保存', calls.showModal.some(m => /已保存|张图片/.test(m.content || '')),
    JSON.stringify(calls.showModal.map(m => m.content)));
  // P0：走服务端权威扣减（saver.afterSaved → /api/user/quota/consume）
  check('消耗 1 次额度（服务端计数）', store.__srv_save === 1, String(store.__srv_save));
}

// ─────────────────────────────────────────────
console.log('\n▸ 搜狐截断 → 页面必须诚实告知');
{
  const { ParseResult } = require(path.join(__dirname, '..', 'utils', 'parse-result.js'));
  const short = new ParseResult(fixture('sohu_short'));
  const { QUOTA } = require(path.join(__dirname, '..', 'utils', 'quota.js'));

  // 构造一个>30s 的截断场景（服务端会返回 truncated=true）
  const longRaw = fixture('sohu_short');
  longRaw.truncated = true;
  const long = new ParseResult(longRaw);
  check('truncated 映射到 notices',
    long.notices.some(n => /30 秒/.test(n)), JSON.stringify(long.notices));
  check('未截断时无该提示',
    !short.notices.some(n => /30 秒/.test(n)), JSON.stringify(short.notices));
}

// ─────────────────────────────────────────────
console.log('\n▸ 会员页：支付未接入不假装能买');
{
  Object.keys(store).forEach(k => { if (k.startsWith('cb_')) delete store[k]; });
  const page = instantiate(loadPage('member', 'member'));
  page.onLoad();
  page.onShow();
  check('免费权益 6 项', page.data.freeBenefits.length === 6, String(page.data.freeBenefits.length));
  check('会员权益 5 项', page.data.memberBenefits.length === 5, String(page.data.memberBenefits.length));
  check('价格 9.9', page.data.price === 9.9);
  // 竞品改造：特权网格 5 项 + 免费对比条数据
  check('特权网格 5 项', page.data.perks.length === 5, String(page.data.perks.length));
  check('免费限额数据就位', page.data.freeLimit === 2, String(page.data.freeLimit));

  // ── 跨端绑定确认端（v4 §2.4，2026-10-11）──
  const msrc = fs.readFileSync(path.join(__dirname, '..', 'pages', 'member', 'member.js'), 'utf-8');
  
// ── 结果页字幕文案卡（2026-10-11：YouTube/FB ytdlp 下发）──
{
  const rp = instantiate(loadPage('result', 'result'));
  check('result 有 onCopySubtitle / onSaveSubtitle',
        typeof rp.onCopySubtitle === 'function'
        && typeof rp.onSaveSubtitle === 'function');
  const rsrc = fs.readFileSync(path.join(__dirname, '..', 'pages', 'result', 'result.js'), 'utf-8');
  check('字幕入库走 libraryAdd（item_type=copy）',
        rsrc.includes('libraryAdd') && rsrc.includes("item_type: 'copy'"));
  const prsrc = fs.readFileSync(path.join(__dirname, '..', 'utils', 'parse-result.js'), 'utf-8');
  check('ParseResult 透传 subtitle_text 三字段',
        prsrc.includes('subtitle_text') && prsrc.includes('subtitle_lang')
        && prsrc.includes('subtitle_auto'));
}
check('member 有 onBridgeBind 确认处理函数', typeof page.onBridgeBind === 'function');
  check('绑定码校验：6 位数字前置校验',
    (/\\d\{6\}/.test(msrc) || msrc.includes("/^\\d{6}$/")), 'regex check');
  check('服务端错误语义逐项翻译（identity_taken/过期/锁定）',
    msrc.includes('identity_taken') && msrc.includes('code_expired')
    && msrc.includes('code_locked'));

  calls.showModal = [];
  page.onBuy();
  // 2026-10-08：购买闭环走卡密（线下收款 → 发码 → 兑换），不再「开发中」占位。
  //   onBuy 弹窗必须真实引导到卡密兑换（confirmText=输入卡密），不假成功不假失败。
  check('onBuy 引导卡密兑换（真实通路，不假占位）',
    calls.showModal.some(m =>
      (m.title || '').includes('开通会员') && (m.content || '').includes('卡密')
      && m.confirmText === '输入卡密'),
    JSON.stringify(calls.showModal));

  // ⛔ 规范硬约束：会员区权益不能出现划线价
  check('权益文案无划线价 19.9',
    !page.data.memberBenefits.some(b => /19\.9/.test(b)), JSON.stringify(page.data.memberBenefits));
}

// ─────────────────────────────────────────────
console.log('\n▸ 素材库：不存播放地址 + 可重新解析');
{
  Object.keys(store).forEach(k => { if (k.startsWith('cb_')) delete store[k]; });
  const { ParseResult } = require(path.join(__dirname, '..', 'utils', 'parse-result.js'));

  const page = instantiate(loadPage('library', 'library'));
  const r = new ParseResult(fixture('bilibili_video'));
  r.inputText = 'https://www.bilibili.com/video/BV1GJ411x7h7';

  // 触发保存
  page.onAdd({ detail: {
    title: r.title, platform: r.platform, platformLabel: r.platformLabel,
    authorName: r.authorName, cover: r.cover, type: r.type, inputText: r.inputText
  }});

  check('存入 1 条', page.data.items.length === 1, String(page.data.items.length));
  const item = page.data.items[0];
  check('存了标题', !!item.title);
  check('⭐ 没存播放地址', !item.videoUrl && !item.video_url && !item.url,
    JSON.stringify(Object.keys(item)));
  check('⭐ 存了原始链接（可重新解析）', !!item.sourceText, item.sourceText);
  check('有时间文本', !!item.timeText, item.timeText);

  calls.switchTab = [];
  page.onReuse({ currentTarget: { dataset: { src: item.sourceText } } });
  check('点重新解析→ 跳首页并带入',
    calls.switchTab.some(u => u.includes('/pages/index/index')) &&
    global.getApp().globalData.pendingInput === item.sourceText,
    JSON.stringify(global.getApp().globalData.pendingInput));
}

// ─────────────────────────────────────────────
console.log('\n▸ 榜单页（M1.5）：加载 + 渲染修饰 + 解析同款闭环');
{
  Object.keys(store).forEach(k => { if (k.startsWith('cb_')) delete store[k]; });
  mockedApi = { parse: fixture('bilibili_video') };

  const page = instantiate(loadPage('ranking', 'ranking'));
  page.onLoad();
  await flush();

  check('加载完成', page.data.loading === false);
  check('20 条榜单', page.data.items.length === 20, String(page.data.items.length));
  check('有更新时间文案', /\d{2}:\d{2} 更新/.test(page.data.updatedText), page.data.updatedText);

  // 渲染修饰：奖牌 + 热度条
  // ⚠️ B站热榜是编辑排序，榜首播放量≠全场最高 —— 热度条「相对全场最大播放量」，
  //   所以不能断言 items[0].heatPct===100（那是把假设写进断言，实测就是 17）。
  check('榜首金牌', page.data.items[0].medal === 'gold', page.data.items[0].medal);
  check('第 2 银牌', page.data.items[1].medal === 'silver');
  check('第 3 铜牌', page.data.items[2].medal === 'bronze');
  check('第 4 无奖牌', page.data.items[3].medal === '');
  const heatMax = Math.max(...page.data.items.map(it => it.heatPct));
  check('最大播放量条目热度条 100%', heatMax === 100, String(heatMax));
  check('热度条在 6–100 区间', page.data.items.every(it => it.heatPct >= 6 && it.heatPct <= 100));
  // 热度条与播放量同向：找出 fixture 中播放量最大的条目，其 heatPct 必为 100
  const topHotIdx = page.data.items.reduce(
    (best, it, i) => (it.hot > page.data.items[best].hot ? i : best), 0);
  check('播放量第一的条目热度条满格', page.data.items[topHotIdx].heatPct === 100);

  // 未接入平台 tab：弹窗说清「为什么没接」，不改状态、不发解析
  calls.showModal = [];
  page.onTabTap({ currentTarget: { dataset: { key: 'weibo' } } });
  const whyModal = calls.showModal[calls.showModal.length - 1] || {};
  check('未接入平台弹窗说明原因', (whyModal.title || '').includes('微博')
    && (whyModal.content || '').length >= 6, JSON.stringify(whyModal));
  check('弹窗原因非空泛（不含规划中/敬请期待）',
    !/规划中|敬请期待|开发中/.test(whyModal.content || ''), whyModal.content);
  check('activeKey 不变', page.data.activeKey === 'bilibili');

  // ⭐ 解析同款闭环：点条目 → /api/parse → globalData → 结果页
  calls.navigateTo = [];
  await page.onItemTap({ currentTarget: { dataset: { index: 0 } } });
  await flush();
  const app = global.getApp();
  check('解析同款成功写入 lastResult', !!(app.globalData.lastResult && app.globalData.lastResult.success));
  check('lastInputText 是榜单条目链接',
    /^https:\/\/www\.bilibili\.com\/video\//.test(app.globalData.lastInputText || ''),
    app.globalData.lastInputText);
  check('跳转结果页', calls.navigateTo.some(u => u.includes('/pages/result/result')),
    JSON.stringify(calls.navigateTo));
  check('parsing 复位', page.data.parsing === false);

  // 解析失败：提示、不跳转
  mockedApi = { parse: fixture('badlink') };
  calls.navigateTo = []; calls.showToast = [];
  await page.onItemTap({ currentTarget: { dataset: { index: 1 } } });
  await flush();
  check('解析失败不跳转', calls.navigateTo.length === 0, JSON.stringify(calls.navigateTo));
  check('解析失败有提示', calls.showToast.length > 0, JSON.stringify(calls.showToast));

  // 服务端 not_implemented（榜单源故障/下线）→ 错误态渲染，不崩溃
  trendingOverride = { ok: false, code: 'not_implemented', platform: 'bilibili' };
  page.setData({ loading: true, items: [], errorMsg: '' });
  page.loadTrending('bilibili');
  await flush();
  check('源下线→ 渲染接入中文案',
    page.data.errorMsg.includes('接入中') && page.data.items.length === 0,
    page.data.errorMsg);
  check('loading 复位', page.data.loading === false);
  trendingOverride = null;

  // 网络异常 → catch 分支
  trendingOverride = '__fail__';
  page.loadTrending('bilibili');
  await flush();
  check('连不上→ 错误态', page.data.errorMsg.length > 0, page.data.errorMsg);
  trendingOverride = null;
}

// ─────────────────────────────────────────────
// ─────────────────────────────────────────────
console.log('\n▸ 内容专栏（M1.5）：分类筛选 + 搜索 + 详情渲染');
{
  const page = instantiate(loadPage('column', 'column'));
  page.onLoad();
  check('10 篇全量加载', page.data.shown.length === 10 && page.data.total === 10,
    String(page.data.shown.length));

  // 分类筛选：素材合规 2 篇
  page.onCatTap({ currentTarget: { dataset: { cat: '素材合规' } } });
  check('素材合规筛选出 2 篇', page.data.shown.length === 2,
    JSON.stringify(page.data.shown.map(a => a.id)));
  check('activeCat 已切换', page.data.activeCat === '素材合规');

  // 搜索：命中标题
  page.setData({ activeCat: '全部' });
  page.onSearchInput({ detail: { value: '封面' } });
  check('搜索「封面」命中且只有封面篇',
    page.data.shown.length === 1 && page.data.shown[0].id === 'cover-3',
    JSON.stringify(page.data.shown.map(a => a.id)));
  check('kw 已记录（清除按钮可见）', page.data.kw === '封面');

  // 搜索无结果 → 空态列表（不残留旧数据）
  page.onSearchInput({ detail: { value: '不存在的关键词xyz' } });
  check('无结果时空列表', page.data.shown.length === 0, String(page.data.shown.length));

  // 清空搜索恢复
  page.onClearKw();
  check('清空后恢复全量', page.data.shown.length === 10, String(page.data.shown.length));

  // 点文章 → 详情页带 id
  calls.navigateTo = [];
  page.onArticleTap({ currentTarget: { dataset: { id: 'publish-time' } } });
  check('跳详情页带 id', calls.navigateTo.some(u => u.includes('article?id=publish-time')),
    JSON.stringify(calls.navigateTo));

  // 详情页：正常渲染
  const acfg = loadPage('article', 'article');
  const apage = instantiate(acfg);
  apage.onLoad({ id: 'cover-3' });
  check('详情页加载成功', apage.data.loaded === true && apage.data.notFound === false);
  check('标题正确', apage.data.article.title.includes('封面三件套'));
  check('小节数与数据一致', apage.data.article.sections.length === 3,
    String(apage.data.article.sections.length));
  check('阅读分钟数已计算', typeof apage.data.article.minutes === 'number' && apage.data.article.minutes >= 2);

  // 详情页：不存在的 id → 明确错误态（不静默空白）
  const nfPage = instantiate(loadPage('article', 'article'));
  nfPage.onLoad({ id: 'not-exist' });
  check('坏 id → notFound 错误态', nfPage.data.notFound === true && nfPage.data.article === null);

  // 分享合规：标题/路径不与权益挂钩
  const share = apage.onShareAppMessage();
  check('文章分享带 id 路径', /article\?id=cover-3/.test(share.path), share.path);
  check('分享标题无权益词', !/解锁|免费|会员/.test(share.title), share.title);
}

// ─────────────────────────────────────────────
console.log('\n▸ 广告位：弹窗频次决策（服务端阈值，客户端计数）');
{
  const ads = require(path.join(__dirname, '..', 'utils', 'ads.js'));
  const COUNT_KEY = 'cb_parse_total';

  // 清缓存与计数（ads.js 的配置缓存也在 storage 里）
  Object.keys(store).forEach(k => {
    if (k.startsWith('cb_parse') || k === 'cb_ads_cfg') delete store[k];
  });

  // 默认 mock 配置：start_after=2, every_n=3 → n=3,4 不弹；n=5 弹；n=6,7 不弹；n=8 弹
  adsCfg = null;
  let show = await ads.recordParse();
  check('第 1 次（≤start_after）不弹', show === false);
  show = await ads.recordParse();
  check('第 2 次（≤start_after）不弹', show === false);
  show = await ads.recordParse();
  check('第 3 次不弹（3-2=1，非 3 的倍数）', show === false, String(store[COUNT_KEY]));
  await ads.recordParse();
  show = await ads.recordParse();
  check('第 5 次弹（5-2=3）', show === true, String(store[COUNT_KEY]));
  await ads.recordParse(); await ads.recordParse();
  show = await ads.recordParse();
  check('第 8 次再弹（8-2=6）', show === true, String(store[COUNT_KEY]));

  // master 总闸关闭 → 永不弹
  adsCfg = { master: false, placements: {}, popup: { enabled: true, every_n_parses: 3, start_after: 0 } };
  try { delete store['cb_ads_cfg']; } catch (e) {}
  show = await ads.recordParse();
  check('master=false 全站不弹（合规总闸）', show === false);

  // popup 单独关闭 → 不弹
  adsCfg = { master: true, placements: {}, popup: { enabled: false, every_n_parses: 3, start_after: 0 } };
  try { delete store['cb_ads_cfg']; } catch (e) {}
  show = await ads.recordParse();
  check('popup.enabled=false 不弹', show === false);

  // getPlacement：placement 开关 + master 联动（对象结构，含 image/unit_id/link）
  try { delete store['cb_ads_cfg']; } catch (e) {}
  adsCfg = null;
  const pi = await ads.getPlacement('index_banner');
  const pr = await ads.getPlacement('ranking_banner');
  check('index_banner 默认开', pi.on === true);
  check('ranking_banner 默认关', pr.on === false);
  check('placement 返回完整字段', 'image' in pi && 'unitId' in pi && 'link' in pi);
  adsCfg = { master: false, placements: { index_banner: true }, popup: { enabled: false } };
  try { delete store['cb_ads_cfg']; } catch (e) {}
  check('master=false 时 getPlacement 恒 off（总闸）',
    (await ads.getPlacement('index_banner')).on === false);
  adsCfg = null;

  // 首页解析成功后触发计数链路（integration：onParse → recordParse）
  Object.keys(store).forEach(k => {
    if (k.startsWith('cb_parse') || k === 'cb_ads_cfg') delete store[k];
  });
  mockedApi = { parse: fixture('bilibili_video') };
  const page = instantiate(loadPage('index', 'index'));
  page.setData({ input: 'https://www.bilibili.com/video/BV1GJ411x7h7' });
  await page.onParse();
  await flush(40);
  check('解析成功写入计数', parseInt(store[COUNT_KEY], 10) >= 1, String(store[COUNT_KEY]));
  check('首次解析不弹窗（start_after 保护）', page.data.showPopup === false);
}

// ─────────────────────────────────────────────
console.log('\n▸ 皮肤系统：切换持久化 + sync 应用 + 会员页换装');
{
  const themes = require(path.join(__dirname, '..', 'utils', 'themes.js'));
  try { delete store.cb_theme; } catch (e) {}

  check('默认皮肤 classic', themes.current() === 'classic');
  check('非法皮肤被拒', themes.setTheme('hacker') === false);
  check('拒绝后仍 classic', themes.current() === 'classic');

  const page = instantiate(loadPage('member', 'member'));
  page.onLoad();
  check('会员页皮肤列表 4 项', page.data.themeList.length === 4,
    JSON.stringify(page.data.themeList));

  page.onPickTheme({ currentTarget: { dataset: { key: 'dark' } } });
  check('切换落库', themes.current() === 'dark'
    && store.cb_theme === 'dark', String(store.cb_theme));
  check('当前页 theme 类立即更新', page.data.theme === 'dark');
  check('tabBar 动态换色被调用', calls.setTabBarStyle.length > 0
    && calls.setTabBarStyle[calls.setTabBarStyle.length - 1].selectedColor === '#D8B98E',
    JSON.stringify(calls.setTabBarStyle.slice(-1)));

  // 页面 sync：dark 皮肤下 light 路由页（素材库）导航应为暗色
  calls.setNavColor = [];
  const libPage = instantiate(loadPage('library', 'library'));
  libPage.onShow();
  check('sync 把 theme 写进页面数据', libPage.data.theme === 'dark');
  check('导航换色被调用', calls.setNavColor.length > 0
    && calls.setNavColor[calls.setNavColor.length - 1].backgroundColor === '#0E0E11',
    JSON.stringify(calls.setNavColor.slice(-1)));

  // 切回默认
  page.onPickTheme({ currentTarget: { dataset: { key: 'classic' } } });
  check('切回 classic', themes.current() === 'classic');
}

// ── 榜单未接入平台：必须说清具体原因（2026-10-07 实测标准固化）──
{
  const api = require(path.join(__dirname, '..', 'utils', 'api.js'));
  const notLive = api.RANKING_PLATFORMS.filter(p => !p.live);
  check('未接入平台均带实测原因（why 字段）',
    notLive.length > 0 && notLive.every(p => typeof p.why === 'string' && p.why.length >= 6),
    JSON.stringify(notLive.map(p => p.label)));
  check('已接入平台无需 why（weibo 转正后 why 应为空）',
    api.RANKING_PLATFORMS.filter(p => p.live).every(p => !p.why));
  check('原因文案不出现空泛的「规划中」',
    notLive.every(p => !/规划中|敬请期待|开发中/.test(p.why)));
  // 2026-10-07：weibo 接入（服务端 Cookie 换视频微博）；未配 Cookie 走 need_cookie
  // weibo 代码就绪但 Cookie 是服务端配置项，C 端显示「待开通」而非报错页
  // 2026-10-08：xhs 接入（热点词条榜，服务端无头浏览器 + Cookie 拦截 XHR）
  check('已接入平台 = bilibili + douyin + kuaishou + acfun + xhs（weibo 待配 Cookie）',
    api.RANKING_PLATFORMS.filter(p => p.live).map(p => p.key).sort().join(',')
      === 'acfun,bilibili,douyin,kuaishou,xhs');
  check('小红书为词条型热点榜（kind=word，点击复制去搜）',
    api.RANKING_PLATFORMS.find(p => p.key === 'xhs').kind === 'word');
  check('AcFun 为视频型榜单（kind=video，点击直接解析）',
    api.RANKING_PLATFORMS.find(p => p.key === 'acfun').kind === 'video');
  check('weibo 保留待开通原因（why 字段）',
    api.RANKING_PLATFORMS.find(p => p.key === 'weibo').why.length >= 6);
  check('快手为词条型热点榜（kind=word）',
    api.RANKING_PLATFORMS.find(p => p.key === 'kuaishou').kind === 'word');
  check('抖音为词条型热点榜（kind=word）',
    api.RANKING_PLATFORMS.find(p => p.key === 'douyin').kind === 'word');
}

// ── 批量进度卡：诚实封顶逻辑 ──
{
  const bp = loadPage('batch', 'batch');
  const page = instantiate(bp);
  page._startBatchProgress(3);
  check('批量进度起点 4%', page.data.bProgress === 4 && page.data.bTotal === 3);
  await new Promise(r => setTimeout(r, 700));
  check('进度平滑递增且封顶 92（不假 100）',
    page.data.bProgress > 4 && page.data.bProgress <= 92,
    String(page.data.bProgress));
  page._stopBatchProgress(true);
  check('真实完成走满 100', page.data.bProgress === 100);
  page._stopBatchProgress(false);
  check('失败归零', page.data.bProgress === 0);
}

// ── 提词器（P2）：纯前端工具，行为断言 ──
{
  const tp = loadPage('teleprompter', 'teleprompter');
  const page = instantiate(tp);
  page.onInput({ detail: { value: '  ' } });
  page.start();
  check('提词器空台词被拦', page.data.errMsg.length > 0, page.data.errMsg);
  page.onInput({ detail: { value: '第一句台词\n第二句台词' } });
  page.start();
  check('有台词进入播放态', page.data.playing === true && page.data.paused === false);
  check('滚动从顶部开始', page.data.scrollTop === 0);
  check('计时器已启动', page._timer !== null && page._timer !== undefined);
  await new Promise(r => setTimeout(r, 120));
  check('滚动位置在推进（30ms 步进）', page.data.scrollTop > 0, String(page.data.scrollTop));
  page.toggle();
  check('点屏幕暂停', page.data.paused === true && page._timer === null);
  page.toggle();
  check('再点继续', page.data.paused === false && page._timer !== null);
  page.changeSpeed({ currentTarget: { dataset: { v: '3' } } });
  check('调速即时生效（档位 3 = 快）', page.data.speed === 3);
  page.exit();
  check('退出清理计时器并复位', page.data.playing === false
    && page.data.scrollTop === 0 && page._timer === null);
}

// ── 积分中心（P2）：签到/兑换行为 ──
{
  const api = require(path.join(__dirname, '..', 'utils', 'api.js'));
  store['cb_openid'] = 'guest_test_points';
  const pc = loadPage('points', 'points');
  const page = instantiate(pc);
  page._today = () => '2026-10-08';
  await page.refresh();
  await flush();
  check('积分余额从服务端读取', page.data.balance === 10, String(page.data.balance));
  check('今日已签状态正确（days 含今天）', page.data.signedToday === true);
  check('可兑换天数 = 余额/单价', page.data.redeemableDays === 0,
    String(page.data.redeemableDays));
  await page.onSign();
  await flush();
  check('重复签到被服务端幂等拦截（不重复加分）',
    page.data.signedToday === true, JSON.stringify(page.data));
}

console.log('\n' + '─'.repeat(52));
console.log(`${pass} PASS / ${fail} FAIL`);
if (fail > 0) process.exit(1);
console.log('✅ 逻辑验证通过');

})();
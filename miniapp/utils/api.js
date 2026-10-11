/**
 * 解析服务 API 客户端
 *
 * ⭐ 契约严格对齐 server/app/main.py（P0 已扩展，2026-10-07）：
 * ```
 * POST /api/parse          { text, quality, no_cache }
 * POST /api/batch          { openid, items:[{text,quality,no_cache}] }
 *                          → 403 超免费条数 / 400 超硬上限
 * POST /api/user/login     { code, device_id, nickname, avatar_url }
 *                          → { openid, via:'wechat|guest', is_member, quota }
 * GET  /api/user/quota?openid=
 * POST /api/user/quota/consume { openid, n } → 耗尽返回 {ok:false,reason:'quota_exhausted'}
 * POST /api/library/add    { openid, item_type, title, platform, author, cover, source_text }
 * GET  /api/library/list?openid=
 * POST /api/library/delete { openid, source_text: item_id }
 * GET  /api/trending?platform=bilibili
 *                          → { ok, platform, cached, updated_at, items:[{rank,title,author,hot,hot_text,cover,url}] }
 *                            未接入平台 → { ok:false, code:'not_implemented' }
 * GET  /api/health
 * ```
 *
 * ⚠️ 超时：批量是串行解析（2C2G），5 条可能 10s+ → 60s
 */

// ── 服务地址 ──
// 开发者工具：本机回环可用；真机走 adb reverse 或局域网 IP
const BASE_URL = 'http://127.0.0.1:8080';

const TIMEOUT = 30000;
const TIMEOUT_BATCH = 60000;

function request(path, options = {}) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: BASE_URL + path,
      method: options.method || 'GET',
      data: options.data || {},
      timeout: options.timeout || TIMEOUT,
      header: {
        'Content-Type': 'application/json',
        ...(options.header || {})
      },
      success(res) {
        // ⭐ 非 2xx 也要把状态码交给调用方 —— 批量的 403（超免费条数）
        //    是业务语义，不能和「连不上」混为一谈
        resolve({ statusCode: res.statusCode, data: res.data });
      },
      fail(err) {
        const msg = /timeout/i.test(err.errMsg || '')
          ? '请求超时，平台可能暂时不可用'
          : '连不上解析服务，请检查服务是否已启动';
        reject(new Error(msg));
      }
    });
  });
}

// ── 单条解析 ──
function parse(text, quality = '720p', noCache = false) {
  return request('/api/parse', {
    method: 'POST',
    data: { text, quality, no_cache: noCache }
  }).then(({ data }) => data);
}

// ── 批量解析 ──
// items 支持两种形态：字符串数组（['url1','url2']）或 {text,quality} 对象数组
// 返回 { statusCode, data } —— 403/400 由调用方按业务处理
function batch(items, openid) {
  return request('/api/batch', {
    method: 'POST',
    timeout: TIMEOUT_BATCH,
    data: {
      openid: openid || '',
      items: items.map(t => typeof t === 'string'
        ? { text: t, quality: '720p' }
        : { text: t.text, quality: t.quality || '720p' })
    }
  });
}

// ── 登录 / 配额 / 素材库 ──
function login(payload) {
  return request('/api/user/login', { method: 'POST', data: payload })
    .then(({ data }) => data);
}

function quota(openid) {
  return request(`/api/user/quota?openid=${encodeURIComponent(openid)}`)
    .then(({ data }) => data);
}

function consumeQuota(openid, n = 1) {
  return request('/api/user/quota/consume', {
    method: 'POST',
    data: { openid, n }
  }).then(({ data }) => data);
}

function libraryAdd(openid, item) {
  return request('/api/library/add', {
    method: 'POST',
    data: { openid, ...item }
  }).then(({ data }) => data);
}

function libraryList(openid, limit = 100) {
  return request(`/api/library/list?openid=${encodeURIComponent(openid)}&limit=${limit}`)
    .then(({ data }) => data);
}

function libraryDelete(openid, itemId) {
  return request('/api/library/delete', {
    method: 'POST',
    data: { openid, source_text: String(itemId) }
  }).then(({ data }) => data);
}

function health() {
  return request('/api/health', { timeout: 5000 }).then(({ data }) => data);
}

// ── 积分中心（P2）──
function points(openid) {
  return request(`/api/points?openid=${encodeURIComponent(openid)}`)
    .then(({ data }) => data);
}
function pointsSign(openid) {
  return request('/api/points/sign', { method: 'POST', data: { openid } })
    .then(({ data }) => data);
}
function pointsRedeem(openid) {
  return request('/api/points/redeem', { method: 'POST', data: { openid } })
    .then(({ data }) => data);
}

// 卡密兑换会员（购买闭环：线下收款 → 发码 → 兑换；支付通道就绪前的主要开通方式）
// 返回 { ok, days, member:{is_member, expire_at}, quota } 或 { ok:false, error }
function redeemCode(openid, code) {
  return request('/api/member/redeem', { method: 'POST', data: { openid, code } })
    .then(({ data }) => data);
}

// ── 账号中台·跨端绑定确认（v4 §2.4，2026-10-11）──
// App/PC 生成 6 位桥接码 → 用户在本端输入 → 设备身份绑到当前账号
// 返回 { statusCode, data }：400 时 data.detail = code_expired / code_not_found /
// code_locked / identity_taken / need_openid / user_not_found（业务语义，不 reject）
function bridgeConfirm(openid, code) {
  return request('/api/auth/bridge/confirm', {
    method: 'POST', data: { openid, code }
  });
}

// 违禁词检测（发布前合规自检；免费 3 次/日基础词库，会员不限次+全类目）
// 返回 { ok, total, risk_level, segments, groups, locked, quota, is_member }
//      或 { ok:false, reason:'quota_exhausted', message }
function bannedCheck(openid, text) {
  return request('/api/banned/check', { method: 'POST', data: { openid, text } })
    .then(({ data }) => data);
}

// 封面防盗链代理（2026-10-11）：平台 CDN 直连偶发裂图 → 服务端中转+缓存
// 非法/空地址原样返回；服务端未知域 403 时前端 binderror 回退原链
function coverProxy(url) {
  if (!url || url.indexOf('http') !== 0) return url;
  return `${BASE_URL}/api/proxy-cover?url=${encodeURIComponent(url)}`;
}

// ── 热门榜单（M1.5 屏 6）──
// 返回 { ok, platform, cached, updated_at, items }
// 未接入平台 ok=false + code='not_implemented'，由调用方渲染「接入中」
function trending(platform) {
  return request(`/api/trending?platform=${encodeURIComponent(platform)}`)
    .then(({ data }) => data);
}

// ── 广告位配置（只读；开关在后台看板改，走 POST 需 API Key）──
function adsConfig() {
  return request('/api/ads/config', { timeout: 8000 }).then(({ data }) => data);
}

// ── 展示映射 ──
const PLATFORM_LABELS = {
  douyin: '抖音',
  bilibili: 'B站',
  haokan: '好看视频',
  sohu: '搜狐',
  weibo: '微博',
  acfun: 'AcFun',
  xiaohongshu: '小红书',
  kuaishou: '快手',
  xigua: '西瓜',
  x: 'X（推特）',
  tiktok: 'TikTok',
  youtube: 'YouTube',
  facebook: 'Facebook'
};

/** 首页平台标签 */
const HOME_PLATFORMS = ['抖音', 'B站', '好看视频', '微博', 'AcFun', '小红书', '快手', '搜狐'];

/** 工具箱占位卡（2026-10-07 用户拍板：展示不开发） */
const TOOLBOX_PLACEHOLDERS = [
  { name: '音频提文案', desc: '视频转文字' },
  { name: '图片提文案', desc: 'OCR 识别' },
  { name: 'AI 创作助手', desc: '创作辅助' },
  { name: '账号工具', desc: '数据分析' },
  { name: '文件转换', desc: '办公文档' },
  { name: '智能修复', desc: '敬请期待' },
];

/** 工具箱真实工具（立即可用） */
const TOOLBOX_LIVE = [
  { name: '素材解析', type: 'parse' },
  { name: '批量解析', type: 'batch', isNew: true },
  { name: '文案提取', type: 'copy' },
  { name: '热门榜单', type: 'rank' },
  { name: '违禁词检测', type: 'banned', isNew: true },
  { name: '运营干货', type: 'column', isNew: true },
  { name: '提词器', type: 'teleprompter', isNew: true },
  { name: 'PDF 工具', type: 'pdftool', isNew: true }
];

/** 首页 Banner 轮播（M1.5+；受广告总开关控制）
 *  path 以 /pages/ 开头；tab=true 走 switchTab，否则 navigateTo */
const INDEX_BANNERS = [
  {
    key: 'member', tag: '会员', cls: 'g1', tab: true,
    title: '9.9 开通会员', sub: '批量 10 条/次 · 高清画质 · 不限次保存',
    path: '/pages/member/member'
  },
  {
    key: 'rank', tag: '热榜', cls: 'g2', tab: true,
    title: '今日热门素材', sub: 'B 站官方热榜 · 点击解析同款',
    path: '/pages/ranking/ranking'
  },
  {
    key: 'column', tag: '干货', cls: 'g3', tab: false,
    title: '运营干货手册', sub: '10 篇创作者实战 · 免费读',
    path: '/pages/column/column'
  }
];

/** 榜单平台 tab（live=false 渲染「接入中」，与服务端 trending.KNOWN_PLATFORMS 对齐） */
/**
 * 榜单平台（M1.5）
 *
 * ⚠️ 接入标准（2026-10-07 实测确立，勿轻易放宽）：
 *   榜单条目必须能构造出「自家 /api/parse 能消化的链接」，
 *   否则点进去没法解析 = 破坏闭环，宁可显示「接入中」。
 *
 * live=false 的原因均为 2026-10-07 逐个接口实测结论（非「还没做」）：
 *   抖音  官方热榜接口通（47 条），但只返回话题词（word/group_id），
 *         无aweme_id；搜索接口补 ID 被风控拦（status_code=2483）→拿不到可解析链接
 *   快手  无公开热榜接口（graphql 需 POST body，m.kuaishou/m.gifshow热榜路径均 404）
 *   微博  weibo.com/ajax/side/hotSearch 通（50 条），但字段里0 条带 mid/objectid；
 *         m.weibo.cn 话题接口需 Cookie（HTTP 432）→ 纯话题词不可解析
 *   （B 站是唯一「榜单条目本身就是视频」的平台，故live=true）
 */
const RANKING_PLATFORMS = [
  { key: 'bilibili', label: 'B站', live: true, kind: 'video' },
  { key: 'douyin', label: '抖音', live: true,
    // 2026-10-07 上线「热点榜」：官方词榜（词条无视频ID）——
    // 点击=复制关键词去抖音搜，不假装能解析
    kind: 'word', why: '' },
  { key: 'kuaishou', label: '快手', live: true, kind: 'word',
    // 2026-10-07 上线「热点榜」：官网首页 SSR 自带热榜模块（用户发现）
    // 词条型，点击=复制关键词去快手搜
    why: '' },
  { key: 'acfun', label: 'AcFun', live: true, kind: 'video',
    // 2026-10-07 上线：无头浏览器抓到榜单 XHR（rest/pc-direct/rank/channel）
    // dougaId → /v/ac{id}，解析器现成 → 视频榜闭环（同 B 站）
    why: '' },
  { key: 'xhs', label: '小红书', live: true, kind: 'word',
    // 2026-10-08 上线「热点榜」：搜索框热榜 XHR（需服务端 Cookie + x-s 签名，
    // 签名由页面 JS 自算 → 服务端无头浏览器注入 Cookie 拦截，不逆向）。
    // 热词无笔记 ID → 词条型，点击=复制关键词去小红书搜。
    // 与解析共用服务端 CB_XHS_COOKIE，Cookie 失效时端点返回 need_cookie。
    why: '' },
  { key: 'weibo', label: '微博', live: false, kind: 'video',
    // 代码已就绪（热搜词→Cookie 换视频微博→oid），但 Cookie 是电脑端
    // 服务配置项，小程序用户无法操作 → tab 显示「待开通」而非报错页。
    // 服务端配好 weibo-cookie.txt 后把 live 改回 true 即上线。
    why: '正在接入，需服务端登录态配置后开放' }
];

module.exports = {
  BASE_URL,
  coverProxy,
  parse,
  batch,
  login,
  quota,
  consumeQuota,
  libraryAdd,
  libraryList,
  libraryDelete,
  health,
  trending,
  adsConfig,
  PLATFORM_LABELS,
  HOME_PLATFORMS,
  RANKING_PLATFORMS,
  TOOLBOX_PLACEHOLDERS,
  points, pointsSign, pointsRedeem,
  redeemCode, bridgeConfirm,
  bannedCheck,
  TOOLBOX_LIVE,
  INDEX_BANNERS
};
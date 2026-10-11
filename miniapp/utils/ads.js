/**
 * 广告位控制（M1.5：服务端配置中心驱动，后台可全量开关）
 *
 * ⭐ 架构：
 *   服务端 /api/ads/config 是唯一事实源（DB 持久化，后台看板可改）。
 *   客户端只读：缓存 5 分钟（storage），banner 位按 placement 查开关。
 *
 * 弹窗广告决策（recordParse → maybePopup）：
 *   · 解析成功才计数（cb_parse_total）
 *   · 前 start_after 次永不弹（新客先体验）
 *   · 之后每 every_n_parses 次弹一次 —— 频次由服务端配置，客户端不改阈值
 *
 * 合规红线（写死在逻辑里，后台也改不掉）：
 *   · 弹窗必须有大而明显的关闭按钮 + 「暂不需要」逃生口
 *   · master=false 时所有位（含弹窗）全部不渲染
 *   · 解析主流程永不被广告阻塞（banner 只在内容区之间，弹窗只在成功后）
 */
const api = require('./api.js');

const CFG_KEY = 'cb_ads_cfg';
const CFG_TTL = 5 * 60 * 1000;          // 5 分钟
const COUNT_KEY = 'cb_parse_total';

/** 拉取配置（带 storage 缓存；失败返回 null —— 广告静默不展示） */
function fetchConfig(force) {
  return new Promise(resolve => {
    if (!force) {
      try {
        const cached = wx.getStorageSync(CFG_KEY);
        if (cached && cached.ts && Date.now() - cached.ts < CFG_TTL && cached.cfg) {
          resolve(cached.cfg);
          return;
        }
      } catch (e) { /* 存储不可用则每次拉取 */ }
    }
    api.adsConfig().then(r => {
      if (r && r.ok && r.ads) {
        try { wx.setStorageSync(CFG_KEY, { ts: Date.now(), cfg: r.ads }); } catch (e) {}
        resolve(r.ads);
      } else {
        resolve(null);
      }
    }).catch(() => resolve(null));
  });
}

/** 某个 banner 位的完整配置（master 总闸 + 单位开关 + 模式二选一）
 *
 * 2026-10-08 升级 v3：模式二选一 + 多图轮播
 *   mode='code'  → 只渲染微信流量主 <ad unit_id>（选广告平台就只显示平台的）
 *   mode='image' → 只渲染自定义图片（1 张静图 / 2~5 张自动轮播，张数由后台决定）
 * 两种配置都存于服务端，切换模式互不覆盖。
 */
function getPlacement(placement) {
  return fetchConfig().then(cfg => {
    if (!cfg || !cfg.master) return { on: false };
    const p = cfg.placements && cfg.placements[placement];
    if (!p) return { on: false };
    const unitId = p.unit_id || '';
    let mode = p.mode || (unitId ? 'code' : 'image');
    if (mode !== 'code' && mode !== 'image') mode = 'image';
    let images = Array.isArray(p.images) ? p.images.filter(Boolean) : [];
    if (!images.length && p.image) images = [p.image];   // 旧结构兼容
    return {
      on: !!p.enabled,
      label: p.label || placement,
      mode,                                              // 'code' | 'image'
      unitId,
      images,
      image: images[0] || '',                            // 旧读侧兼容
      link: p.link || ''
    };
  });
}

/** 弹窗配置（频次决策 + 可选自定义图/链接） */
function getPopup() {
  return fetchConfig().then(cfg => {
    if (!cfg || !cfg.popup) return { on: false };
    return {
      on: !!cfg.popup.enabled,
      image: cfg.popup.image || '',
      unitId: cfg.popup.unit_id || '',
      link: cfg.popup.link || ''
    };
  });
}

/**
 * 记一次解析成功，返回是否应弹窗。
 * 决策完全基于服务端配置的阈值，客户端只做计数。
 */
function recordParse() {
  let n = 0;
  try { n = parseInt(wx.getStorageSync(COUNT_KEY), 10) || 0; } catch (e) {}
  n += 1;
  try { wx.setStorageSync(COUNT_KEY, String(n)); } catch (e) {}
  return fetchConfig().then(cfg => {
    if (!cfg || !cfg.master || !cfg.popup || !cfg.popup.enabled) return false;
    const start = cfg.popup.start_after || 0;
    const every = cfg.popup.every_n_parses || 3;
    if (n <= start) return false;
    return (n - start) % every === 0;
  });
}

module.exports = { fetchConfig, getPlacement, getPopup, recordParse };

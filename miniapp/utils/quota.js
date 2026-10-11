/**
 * 登录 + 免费配额管理（P0：切换为服务端权威）
 *
 * ⭐ 架构变化（2026-10-07）：
 *   旧版：本地 wx.storage 计数 —— 卸载重置、可被清缓存绕过
 *   新版：服务端 SQLite 权威（db.get_quota），本地只做**乐观缓存**：
 *     · 先用缓存值渲染（秒开）
 *     · 关键动作前后与服务器同步
 *     · 服务端耗尽返回 quota_exhausted → 客户端拦截
 *
 * 登录策略：
 *   · wx.login 拿 code → 服务端 code2Session 换正式 openid（需 WX_SECRET）
 *   · 服务端未配 secret（M1.5 支付前）→ 降级游客态：
 *     首次生成 device_id（随机 UUID 存 storage），openid = guest_{device_id}
 *   · 两种形态对客户端透明 —— 只拿 openid 用
 */

const api = require('./api.js');

const KEY_OPENID = 'cb_openid';
const KEY_DEVICE = 'cb_device_id';
const KEY_QUOTA = 'cb_quota_cache';   // { save_left, save_limit, batch_limit, is_member, ts }

const QUOTA = {
  /** 与服务端 config.py / db.py 三处同步 —— 改一处要同步另两处 */
  VIDEO_SAVE_PER_DAY: 2,
  FREE_MAX_HEIGHT: 720,
  BATCH_LIMIT_FREE: 3,
  MEMBER_PRICE: 9.9,

  _deviceId() {
    let id = wx.getStorageSync(KEY_DEVICE);
    if (!id) {
      id = 'd' + Date.now().toString(36) +
           Math.random().toString(36).slice(2, 10);
      wx.setStorageSync(KEY_DEVICE, id);
    }
    return id;
  },

  _quotaCache() {
    try {
      const c = wx.getStorageSync(KEY_QUOTA);
      // 缓存跨天失效（服务端按天重置）
      if (c && c.day === new Date().toDateString()) return c;
    } catch (e) { }
    return null;
  },

  _setQuotaCache(q) {
    wx.setStorageSync(KEY_QUOTA, { ...q, day: new Date().toDateString() });
  },

  /**
   * 确保已登录，返回 openid。
   * 已有 openid 直接返回；否则走 wx.login → 服务端。
   */
  ensureLogin() {
    const cached = wx.getStorageSync(KEY_OPENID);
    if (cached) return Promise.resolve(cached);

    return new Promise((resolve) => {
      wx.login({
        success: res => {
          api.login({
            code: res.code || '',
            device_id: QUOTA._deviceId()
          }).then(r => {
            wx.setStorageSync(KEY_OPENID, r.openid);
            if (r.quota) QUOTA._setQuotaCache(r.quota);
            resolve(r.openid);
          }).catch(() => {
            // 服务不可达也要给身份（离线兜底），联网后重新校准
            resolve('offline_' + QUOTA._deviceId());
          });
        },
        fail: () => resolve('offline_' + QUOTA._deviceId())
      });
    });
  },

  /** 拉取服务端配额（登录后调用）。失败时回退本地缓存。 */
  refresh() {
    return QUOTA.ensureLogin().then(openid => {
      if (openid.startsWith('offline_')) {
        return QUOTA._quotaCache() || QUOTA._fallbackQuota();
      }
      return api.quota(openid).then(q => {
        QUOTA._setQuotaCache(q);
        return q;
      }).catch(() => QUOTA._quotaCache() || QUOTA._fallbackQuota());
    });
  },

  /** 乐观读（同步、零请求）：首页首屏渲染用 */
  cachedQuota() {
    return QUOTA._quotaCache() || QUOTA._fallbackQuota();
  },

  _fallbackQuota() {
    return {
      is_member: false,
      save_used: 0,
      save_limit: QUOTA.VIDEO_SAVE_PER_DAY,
      save_left: QUOTA.VIDEO_SAVE_PER_DAY,
      batch_limit: QUOTA.BATCH_LIMIT_FREE
    };
  },

  /**
   * 保存成功后调用：服务端扣减并返回最新配额。
   * 服务端耗尽 → { ok:false, reason:'quota_exhausted' }
   * 离线 → ok:true + 本地扣（乐观），联网后以服务端为准。
   */
  consume(n = 1) {
    const openid = wx.getStorageSync(KEY_OPENID);
    if (!openid || openid.startsWith('offline_')) {
      // 离线乐观扣减
      const q = QUOTA.cachedQuota();
      q.save_used = (q.save_used || 0) + n;
      if (!q.is_member) q.save_left = Math.max(0, (q.save_left ?? 2) - n);
      QUOTA._setQuotaCache(q);
      return Promise.resolve({ ok: true, quota: q, offline: true });
    }
    return api.consumeQuota(openid, n).then(r => {
      if (r.quota) QUOTA._setQuotaCache(r.quota);
      return r;
    });
  },

  /** 批量条数上限（乐观读） */
  batchLimit() {
    return QUOTA.cachedQuota().batch_limit || QUOTA.BATCH_LIMIT_FREE;
  },

  isMember() {
    return !!QUOTA.cachedQuota().is_member;
  },

  memberBenefits() {
    return ['视频保存不限次', '图集保存不限次', '批量解析不限条数',
            '1080P 高清画质', '全免广告 · 永久有效'];
  },

  freeBenefits() {
    return ['解析不限次数', `视频每日 ${QUOTA.VIDEO_SAVE_PER_DAY} 次`,
            '图集每月 3 次', '批量单次 3 条', `${QUOTA.FREE_MAX_HEIGHT}P 画质`,
            '有广告'];
  }
};

module.exports = { QUOTA };
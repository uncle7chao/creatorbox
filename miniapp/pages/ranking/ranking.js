/**
 * 屏 6 · 热门榜单（M1.5）
 *
 * 定位：解析是低频需求，榜单是高频流量入口（竞品拆解结论 —— 抄轻抖打法）
 *
 * ⭐ 数据契约（server/app/trending.py）：
 *   { ok, platform, cached, updated_at, items:[{rank,title,author,hot,hot_text,cover,url}] }
 * - 条目 url 保证可进 /api/parse →「解析同款」闭环，点击直接走首页同款解析链路
 * - 未接入平台 ok=false + code='not_implemented' → 渲染「接入中」态，不造假数据
 * - 服务端缓存 10 分钟；本页不做下拉假刷新，只显示更新时间
 */
const api = require('../../utils/api.js');
const { ParseResult, makeFailure } = require('../../utils/parse-result.js');
const { QUOTA } = require('../../utils/quota.js');
const themeUtil = require('../../utils/themes.js');

const FREE_MAX_HEIGHT = QUOTA.FREE_MAX_HEIGHT;   // 720P，与首页一致

Page({
  data: {
    theme: 'classic',
    platforms: api.RANKING_PLATFORMS,
    activeKey: 'bilibili',
    activeLabel: 'B站',

    loading: true,
    errorMsg: '',
    items: [],          // 渲染用：rank/title/author/hot_text/cover/url/heatPct/medal
    updatedText: '',

    parsing: false      // 防重复点击「解析同款」
  },

  onLoad() {
    this.loadTrending(this.data.activeKey);
  },

  onShow() {
    themeUtil.sync(this);
    // 从结果页返回后刷新解析状态；榜单本身走服务端缓存，不必重拉
  },

  /** 拉取某平台榜单（未接入平台由服务端 code 区分，不猜） */
  loadTrending(key) {
    const p = api.RANKING_PLATFORMS.find(x => x.key === key);
    if (!p) return;
    if (!p.live) {
      // tab 上就该是置灰态，这里是兜底（正常流程点不进来）
      wx.showToast({ title: `${p.label}热榜接入中`, icon: 'none' });
      return;
    }
    this.setData({ loading: true, errorMsg: '', activeKey: key, activeLabel: p.label });
    api.trending(key)
      .then(r => {
        if (!r || r.ok !== true || !Array.isArray(r.items)) {
          // need_cookie（微博未配 Cookie）/ upstream_error / not_implemented
          // 服务端 message 已是面向用户的完整话术，直接渲染
          const msg = r && r.code === 'need_cookie'
            ? `${p.label}榜单正在开通中，敬请期待`
            : (r && r.message)
              || (r && r.code === 'not_implemented'
                ? `${p.label}热榜接入中` : '榜单暂时不可用');
          this.setData({ loading: false, errorMsg: msg, items: [],
            needCookie: r && r.code === 'need_cookie' });
          return;
        }
        const items = this.decorate(r.items);
        this.setData({
          loading: false,
          items,
          updatedText: this.fmtTime(r.updated_at)
        });
      })
      .catch(e => {
        this.setData({
          loading: false,
          errorMsg: e.message || '连不上解析服务',
          items: []
        });
      });
  },

  /** 渲染修饰：奖牌徽章 + 热度条百分比（相对榜首） */
  decorate(items) {
    const maxHot = items.reduce((m, it) => Math.max(m, it.hot || 0), 0) || 1;
    return items.map(it => ({
      ...it,
      medal: it.rank <= 3 ? ['gold', 'silver', 'bronze'][it.rank - 1] : '',
      heatPct: Math.max(6, Math.round((it.hot || 0) / maxHot * 100))
    }));
  },

  fmtTime(ts) {
    if (!ts) return '';
    const d = new Date(ts * 1000);
    const pad = n => (n < 10 ? '0' + n : '' + n);
    return `${pad(d.getHours())}:${pad(d.getMinutes())} 更新`;
  },

  /** 切平台 tab */
  onTabTap(e) {
    const key = e.currentTarget.dataset.key;
    if (!key || key === this.data.activeKey) return;
    const p = api.RANKING_PLATFORMS.find(x => x.key === key);
    if (p && !p.live) {
      // 说清「为什么没接」而不是只说接入中（原因均为逐接口实测结论）
      wx.showModal({
        title: `${p.label}热榜暂未开放`,
        content: p.why || '该平台暂未提供可解析的热榜数据',
        showCancel: false,
        confirmText: '知道了'
      });
      return;
    }
    this.loadTrending(key);
  },

  /** ⭐ 解析同款 —— 与首页 onParse 同链路：parse → ParseResult → globalData → 结果页 */
  async onItemTap(e) {
    // 热点词条（抖音/快手/小红书词榜）：无视频 ID，点击=复制关键词去对应 App 搜
    const it0 = this.data.items[Number(e.currentTarget.dataset.index)];
    if (it0 && it0.type === 'word') {
      wx.setClipboardData({
        data: it0.title,
        // 用当前平台名（activeLabel），不再写死「抖音」
        success: () => wx.showToast({ title: `关键词已复制，去${this.data.activeLabel || '对应'}搜索`, icon: 'none', duration: 2200 })
      });
      return;
    }
    if (this.data.parsing) return;
    const idx = e.currentTarget.dataset.index;
    const item = this.data.items[idx];
    if (!item || !item.url) return;

    this.setData({ parsing: true });
    wx.showLoading({ title: '解析中…', mask: true });
    try {
      // 同上：openid 用于按人限流（榜单入口同样会撞共享 IP）
      const openid = await QUOTA.ensureLogin();
      const raw = await api.parse(item.url, `${FREE_MAX_HEIGHT}p`, false, openid);
      const r = new ParseResult(raw);
      if (!r.success) {
        wx.hideLoading();
        wx.showToast({ title: r.error || '解析失败', icon: 'none', duration: 2500 });
        return;
      }
      // 与首页同一约定：globalData 传数据，避免 URL 塞长文案
      // ⚠️ 必须用 getApp()，不要裸 app（单测环境无 app 全局变量）
      getApp().globalData.lastResult = r;
      getApp().globalData.lastInputText = item.url;
      wx.hideLoading();
      wx.navigateTo({ url: '/pages/result/result' });
    } catch (e2) {
      wx.hideLoading();
      const r = makeFailure(e2.message || '解析失败');
      wx.showToast({ title: r.error, icon: 'none', duration: 2500 });
    } finally {
      this.setData({ parsing: false });
    }
  },

  onRetry() {
    this.loadTrending(this.data.activeKey);
  },

  onShareAppMessage() {
    return {
      title: '热门素材榜',
      path: '/pages/ranking/ranking'
    };
  }
});

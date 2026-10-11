/**
 * 屏 1 · 解析首页
 *
 * ⭐ 严格按 docs/小程序UI设计规范.md：
 *   · 深色区（brand-900渐变）+ 悬浮白卡（-2.25rem 上提）
 *   · 主文案「去掉水印 只要干净素材」20px —— 转化核心
 *   · 额度三指标常驻，「不限」字号最大（v3 定位：解析不限次）
 *   · 平台标签区右侧「全部已验证」← v3 韧性定位的可视化
 *   · 底部免责灰字 11px（规范 3.13 硬要求，但不显眼）
 *
 * 采集通道：本期只做「手动粘贴」。
 * ⏳剪贴板监听与分享接收需等 M0-V1 探针结果（见 m0-probe/测试清单.md），
 *    平台自定义 scheme 可能走私有通道，不先验证就做会白做。
 */
const api = require('../../utils/api.js');
const { ParseResult, makeFailure } = require('../../utils/parse-result.js');
const { QUOTA } = require('../../utils/quota.js');
const saver = require('../../utils/saver.js');
const ads = require('../../utils/ads.js');
const themeUtil = require('../../utils/themes.js');

const FREE_MAX_HEIGHT = QUOTA.FREE_MAX_HEIGHT;   // 720P
const SAVE_QUOTA = QUOTA.VIDEO_SAVE_PER_DAY;     // 每日 2 次

Page({
  data: {
    theme: 'classic',
    input: '',
    parsing: false,
    errorMsg: '',

    // 解析进度动画（_startProgress 驱动）
    progress: 0,
    stepText: '',

    // 弹窗广告（服务端配置频次与自定义素材；ads.recordParse 决定）
    showPopup: false,
    popupImage: '',
    popupLink: '',

    // Banner 轮播 slides（首页运营位，受广告总开关控制）
    banners: api.INDEX_BANNERS,

    // 顶部自宣传轮播（后台「首页顶部轮播」位配图后替换默认标题 hero）
    heroImages: [],
    heroLink: '',

    // 额度（数值来自 quota.js，改额度只改那一处）
    savedToday: 0,
    saveQuota: SAVE_QUOTA,

    // 服务状态
    serviceOk: true,
    serviceMsg: '已连接',
    platformCount: 0,

    platforms: api.HOME_PLATFORMS,
    // 平台标签（带 key → 图标文件名）；名字与 HOME_PLATFORMS 顺序一致
    platformTags: api.HOME_PLATFORMS.map(n => ({
      key: { '抖音': 'douyin', 'B站': 'bilibili', '好看视频': 'haokan',
             '微博': 'weibo', 'AcFun': 'acfun', '小红书': 'xhs',
             '快手': 'kuaishou', '搜狐': 'sohu' }[n] || 'douyin',
      name: n
    })),
    freeMaxHeight: FREE_MAX_HEIGHT
  },

  onLoad() {
    this.checkService();
    this.refreshQuota();
    this.loadHero();
  },

  onShow() {
    themeUtil.sync(this);
    // 从其他页返回时刷新（服务可能已被关掉，额度也可能已消耗）
    this.checkService();
    this.refreshQuota();
  },

  /** 顶部自宣传轮播：后台「首页顶部轮播」位（1~3 张；未配置则保留默认标题 hero） */
  loadHero() {
    ads.getPlacement('hero_banner').then(p => {
      if (p.on && Array.isArray(p.images) && p.images.length) {
        this.setData({ heroImages: p.images.slice(0, 3), heroLink: p.link || '' });
      } else if (this.data.heroImages.length) {
        this.setData({ heroImages: [], heroLink: '' });
      }
    });
  },

  /** 轮播图点击 → 后台配置的跳转（可选） */
  onHeroTap() {
    const link = this.data.heroLink;
    if (!link) return;
    const tabs = ['pages/index/index', 'pages/toolbox/toolbox',
      'pages/ranking/ranking', 'pages/library/library', 'pages/member/member'];
    if (tabs.some(t => link.indexOf(t) === 0)) {
      wx.switchTab({ url: link });
    } else {
      wx.navigateTo({ url: link });
    }
  },

  /** 健康检查 —— 服务没起要明确告诉用户，不能静默失败 */
  checkService() {
    api.health()
      .then(h => {
        this.setData({
          serviceOk: !!h.ready,
          serviceMsg: h.ready ? '已连接' : '服务未就绪',
          platformCount: (h.platforms || []).length
        });
      })
      .catch(() => {
        this.setData({
          serviceOk: false,
          serviceMsg: '服务未连接',
          platformCount: 0
        });
      });
  },

  refreshQuota() {
    // ⭐ P0：切服务端权威 —— 先乐观渲染缓存，再静默校准
    this.setData({ savedToday: QUOTA.cachedQuota().save_used || 0 });
    QUOTA.refresh().then(q => {
      this.setData({
        savedToday: q.save_used || 0,
        saveQuota: q.is_member ? 0 : (q.save_limit || SAVE_QUOTA)
      });
    });
  },

  // ── 工具行导航 ──
  navBatch() { wx.navigateTo({ url: '/pages/batch/batch' }); },
  navLibrary() { wx.switchTab({ url: '/pages/library/library' }); },
  navToolbox() { wx.switchTab({ url: '/pages/toolbox/toolbox' }); },
  navRanking() {
    // M1.5：榜单已上线（B站热榜），tabBar 与工具行双入口
    wx.switchTab({ url: '/pages/ranking/ranking' });
  },

  /**
   * ⭐ 提取文案（双产出第二路径，抄轻抖）
   * 解析 → meta.description 有值 → 直接复制到剪贴板（比跳结果页少一步）
   * 无文案（接口不下发，如 AcFun）→ 明确告知，不复制空串
   */
  async onExtractCopy() {
    const text = (this.data.input || '').trim();
    if (!text) {
      this.setData({ errorMsg: '请先粘贴链接或分享内容' });
      return;
    }
    if (this.data.parsing) return;
    this.setData({ parsing: true, errorMsg: '' });
    wx.showLoading({ title: '提取文案…', mask: true });
    try {
      const raw = await api.parse(text, `${FREE_MAX_HEIGHT}p`);
      const r = new ParseResult(raw);
      if (!r.success) {
        this.setData({ errorMsg: r.error || '解析失败' });
        wx.showToast({ title: r.error || '解析失败', icon: 'none' });
        return;
      }
      // 文案来源优先级：description（接口文案）→ title（降级，标明来源）
      const copy = r.description || r.title;
      if (!copy) {
        wx.showToast({ title: '该内容未提供文案', icon: 'none', duration: 2500 });
        return;
      }
      const ok = await saver.copyText(copy);
      if (ok) {
        wx.showToast({ title: '文案已复制到剪贴板', icon: 'success' });
      } else {
        wx.showToast({ title: '复制失败，请重试', icon: 'none' });
      }
    } catch (e) {
      wx.showToast({ title: e.message || '提取失败', icon: 'none' });
    } finally {
      wx.hideLoading();
      this.setData({ parsing: false });
    }
  },

  // ── 输入 ──
  onInput(e) {
    this.setData({ input: e.detail.value, errorMsg: '' });
  },

  /** 读剪贴板 */
  pasteFromClipboard() {
    wx.getClipboardData({
      success: res => {
        const text = (res.data || '').trim();
        if (!text) {
          wx.showToast({ title: '剪贴板是空的', icon: 'none' });
          return;
        }
        this.setData({ input: text, errorMsg: '' });
      },
      fail: () => {
        wx.showToast({ title: '读不到剪贴板，请手动粘贴', icon: 'none' });
      }
    });
  },

  /** 清空输入 */
  clearInput() {
    this.setData({ input: '', errorMsg: '' });
  },

  // ── 解析进度动画（竞品骨架：分段文案 + 渐进进度条，真完成才到 100）──
  _startProgress() {
    this._stopProgress(true);
    this.setData({ progress: 2, stepText: '识别链接…' });
    this._progTimer = setInterval(() => {
      const p = this.data.progress;
      // 前段快、后段慢、92% 封顶等真实结果 —— 不学竞品假跳 100%
      const np = p < 70 ? p + 6 : p < 90 ? p + 2 : Math.min(92, p + 1);
      const step = np < 30 ? '识别链接…'
        : np < 70 ? '连接平台…'
        : np < 92 ? '提取内容…'
        : '即将完成';
      this.setData({ progress: np, stepText: step });
    }, 120);
  },

  _stopProgress(done) {
    if (this._progTimer) {
      clearInterval(this._progTimer);
      this._progTimer = null;
    }
    this.setData(done
      ? { progress: 100, stepText: '完成' }
      : { progress: 0, stepText: '' });
  },

  // ── 解析 ──
  async onParse() {
    const text = (this.data.input || '').trim();
    if (!text) {
      this.setData({ errorMsg: '请先粘贴链接或分享内容' });
      return;
    }
    if (this.data.parsing) return;

    this.setData({ parsing: true, errorMsg: '' });
    this._startProgress();

    try {
      const raw = await api.parse(text, `${FREE_MAX_HEIGHT}p`);
      const r = new ParseResult(raw);

      if (!r.success) {
        //触点③：解析失败时给「看广告重试」的入口
        this._stopProgress(false);
        this.setData({ errorMsg: r.error || '解析失败，请检查链接是否有效' });
        wx.showModal({
          title: '解析失败',
          content: r.error || '链接可能已失效，或该内容需要登录才能访问',
          showCancel: true,
          cancelText: '知道了',
          confirmText: '重试',
          success: res => {
            if (res.confirm) this.onParse();
          }
        });
        return;
      }

      // 结果页通过 globalData 传数据 —— 避免 URL 里塞几百字的分享文案
      // ⚠️ 必须用 getApp() 取，不要写裸的 app（小程序运行时才有 app 全局变量，
      //    单测/工具环境里不存在，会直接抛 app is not defined）
      getApp().globalData.lastResult = r;
      getApp().globalData.lastInputText = text;

      this._stopProgress(true);
      // 广告：解析成功计数 → 服务端配置决定是否弹窗（合规：频次封顶+可关）
      ads.recordParse().then(show => {
        if (!show) return;
        ads.getPopup().then(pc => {
          this.setData({ showPopup: true, popupImage: pc.image, popupLink: pc.link });
        });
      }).catch(() => {});
      wx.navigateTo({ url: '/pages/result/result' });
    } catch (e) {
      this._stopProgress(false);
      const r = makeFailure(e.message || '解析失败');
      this.setData({ errorMsg: r.error });
      wx.showToast({ title: r.error, icon: 'none', duration: 2500 });
    } finally {
      this.setData({ parsing: false });
    }
  },

  /** 弹窗广告：关闭（合规：随时可关，不与任何权益挂钩） */
  onPopupClose() {
    this.setData({ showPopup: false });
  },

  /** 弹窗广告：点击主行动 → 服务端配置的 link（默认会员页） */
  onPopupGo() {
    this.setData({ showPopup: false });
    const link = this.data.popupLink;
    if (link) {
      const tabs = ['pages/index/index', 'pages/toolbox/toolbox',
        'pages/ranking/ranking', 'pages/library/library', 'pages/member/member'];
      if (tabs.some(t => link.indexOf(t) === 0)) wx.switchTab({ url: link });
      else wx.navigateTo({ url: link });
      return;
    }
    wx.switchTab({ url: '/pages/member/member' });
  },

  /** 免责灰字 → 合规页（规范 3.13 要求投诉渠道可达） */
  navCompliance() {
    wx.navigateTo({ url: '/pages/compliance/compliance' });
  },

  onShareAppMessage() {
    // ⚠️ 合规红线：绝不能做成「分享后解锁功能」。
    //    这里只是普通的转发，不与任何权益挂钩。
    return {
      title: '素材解析',
      path: '/pages/index/index'
    };
  }
});
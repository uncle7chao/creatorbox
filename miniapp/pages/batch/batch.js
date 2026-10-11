/**
 * 批量解析页（P0，2026-10-07）
 *
 * 交互规则（竞品工具箱验证）：
 *   · 多行输入，一行一条
 *   · 免费单次 3 条 / 会员 10 条 —— **服务端权威**（403 时弹会员引导）
 *   · 串行解析，一条失败不阻塞其他
 *   · 结果逐条显示成功/失败，勾选只对成功项
 *   · 保存走 saver.js（与结果页同一套逻辑）
 */
const api = require('../../utils/api.js');
const { ParseResult } = require('../../utils/parse-result.js');
const { QUOTA } = require('../../utils/quota.js');
const saver = require('../../utils/saver.js');
const themeUtil = require('../../utils/themes.js');

Page({
  data: {
    theme: 'classic',
    input: '',
    count: 0,
    parsing: false,
    // 批量进度卡（2026-10-07：替换静态 showLoading，首页同款诚实进度）
    bProgress: 0,
    bTotal: 0,
    results: [],        // {idx, ok, title, platform, cover, urls, kind, error}
    okCount: 0,
    failCount: 0,
    selected: {},       // idx -> true
    selectedCount: 0,
    batchLimit: 3,
    errMsg: ''
  },

  onShow() {
    themeUtil.sync(this);
  },

  onLoad() {
    QUOTA.ensureLogin().then(() => {
      this.setData({ batchLimit: QUOTA.batchLimit() });
    });
  },

  onInput(e) {
    const lines = (e.detail.value || '').split('\n')
      .map(s => s.trim()).filter(Boolean);
    this.setData({ input: e.detail.value, count: lines.length, errMsg: '' });
  },

  async onParse() {
    const lines = (this.data.input || '').split('\n')
      .map(s => s.trim()).filter(Boolean);
    if (!lines.length) {
      this.setData({ errMsg: '请先粘贴链接（每行一条）' });
      return;
    }
    if (this.data.parsing) return;

    const limit = QUOTA.batchLimit();
    if (lines.length > limit) {
      // ⭐ 服务端也会拦（403），这里先拦省一次请求
      wx.showModal({
        title: '超出单次条数',
        content: `当前身份单次最多 ${limit} 条（已粘贴 ${lines.length} 条）。开通会员单次可解析 10 条。`,
        confirmText: '了解会员',
        cancelText: '只解析前' + limit + '条',
        success: res => {
          if (res.confirm) wx.navigateTo({ url: '/pages/member/member' });
          else {
            this.setData({ input: lines.slice(0, limit).join('\n') });
            this.startParse(lines.slice(0, limit));
          }
        }
      });
      return;
    }
    this.startParse(lines);
  },

  /** 批量进度：平滑递增至 92% 封顶等真实结果（真完成才到 100，不假进度） */
  _startBatchProgress(total) {
    this._bpTimer && clearInterval(this._bpTimer);
    this.setData({ bProgress: 4, bTotal: total });
    this._bpTimer = setInterval(() => {
      const cur = this.data.bProgress;
      if (cur < 92) this.setData({ bProgress: Math.min(92, cur + (cur < 60 ? 5 : 2)) });
    }, 320);
  },

  _stopBatchProgress(done) {
    this._bpTimer && clearInterval(this._bpTimer);
    this._bpTimer = null;
    this.setData({ bProgress: done ? 100 : 0 });
  },

  async startParse(lines) {
    this.setData({ parsing: true, errMsg: '', results: [], selected: {}, selectedCount: 0 });
    this._startBatchProgress(lines.length);

    try {
      const openid = wx.getStorageSync('cb_openid') || '';
      const { statusCode, data } = await api.batch(lines, openid);

      if (statusCode === 403) {
        // 服务端权威拦截（本地条数没超但配额变化等边界）
        this._stopBatchProgress(false);
        this.setData({ parsing: false });
        wx.showModal({
          title: '超出单次条数',
          content: (data && data.detail) || '免费用户单次最多 3 条，开通会员可解析 10 条。',
          confirmText: '了解会员',
          showCancel: false,
          success: res => { if (res.confirm) wx.navigateTo({ url: '/pages/member/member' }); }
        });
        return;
      }
      if (statusCode === 400) {
        this._stopBatchProgress(false);
        this.setData({ parsing: false, errMsg: (data && data.detail) || '超出单次上限' });
        return;
      }

      const results = [];
      (data.results || []).forEach((raw, i) => {
        if (!raw.success) {
          results.push({
            idx: i, ok: false,
            title: raw.error || '解析失败',
            meta: (raw.platform ? raw.platform : '') + ' · ' + (raw.error || ''),
            kind: '', urls: [], cover: ''
          });
          return;
        }
        const pr = new ParseResult(raw);
        const urls = pr.isImage
          ? pr.images.map(im => im.url).filter(Boolean)
          : [(pr.recommendedOption && pr.recommendedOption.url) || pr.videoUrl];
        results.push({
          idx: i, ok: true,
          title: pr.title || '（无标题）',
          meta: `${pr.platformLabel} · ${pr.isImage ? pr.imageCount + ' 张图' : (pr.durationText || '视频')}`,
          kind: pr.isImage ? 'image' : 'video',
          urls, cover: pr.cover || (pr.images[0] ? pr.images[0].url : ''),
          mergeRequired: pr.mergeRequired, titleHint: pr.titleHint
        });
      });

      const okCount = results.filter(r => r.ok).length;
      const selected = {};
      results.forEach(r => { if (r.ok) selected[r.idx] = true; });

      this.setData({
        results, okCount, failCount: results.length - okCount,
        selected, selectedCount: okCount
      });
    } catch (e) {
      this._stopBatchProgress(false);
      this.setData({ errMsg: e.message || '批量解析失败' });
    } finally {
      // 真实完成：进度走满 100 再收卡
      if (this.data.bProgress > 0) {
        this._stopBatchProgress(true);
        setTimeout(() => this.setData({ parsing: false, bProgress: 0 }), 350);
      } else {
        this.setData({ parsing: false });
      }
    }
  },

  onToggle(e) {
    const idx = Number(e.currentTarget.dataset.idx);
    const item = this.data.results[idx];
    if (!item || !item.ok) return;          // 失败项不可选
    const selected = { ...this.data.selected };
    if (selected[idx]) delete selected[idx];
    else selected[idx] = true;
    this.setData({ selected, selectedCount: Object.keys(selected).length });
  },

  onSelectAll() {
    const selected = {};
    this.data.results.forEach(r => { if (r.ok) selected[r.idx] = true; });
    this.setData({ selected, selectedCount: Object.keys(selected).length });
  },

  /** 保存已选（逐条：图集存全部图，视频存推荐档） */
  async onSave() {
    if (this.data.parsing) return;
    const chosen = this.data.results.filter(r => r.ok && this.data.selected[r.idx]);
    if (!chosen.length) {
      wx.showToast({ title: '请先勾选要保存的结果', icon: 'none' });
      return;
    }

    // AcFun 合并项提示并跳过
    const mergeItems = chosen.filter(c => c.mergeRequired);
    const savable = chosen.filter(c => !c.mergeRequired);
    if (!savable.length) {
      wx.showToast({ title: '所选内容需服务端合并，暂不可直接保存', icon: 'none', duration: 2500 });
      return;
    }

    this.setData({ parsing: true });
    wx.showLoading({ title: '保存中…', mask: true });

    let savedUnits = 0;
    for (const item of savable) {
      if (item.kind === 'image') {
        const r = await saver.saveMany(item.urls, 'jpg');
        if (r.done > 0) savedUnits++;
      } else {
        const r = await saver.saveVideo(item.urls[0]);
        if (r.saved) savedUnits++;
      }
    }

    wx.hideLoading();
    this.setData({ parsing: false });

    if (savedUnits > 0) {
      // 服务端扣配额（免费每日 2 次 —— 每个内容单元算 1 次）
      saver.afterSaved(savedUnits).then(() => {
        QUOTA.refresh();
      });
      wx.showModal({
        title: '批量保存完成',
        content: `成功 ${savedUnits} 条` +
          (mergeItems.length ? `，另有 ${mergeItems.length} 条需服务端合并已跳过` : ''),
        showCancel: false
      });
    } else {
      wx.showToast({ title: '保存失败，请检查网络', icon: 'none' });
    }
  },

  navHome() { wx.switchTab({ url: '/pages/index/index' }); }
});
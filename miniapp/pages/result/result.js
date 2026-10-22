/**
 * 屏 2 · 结果页
 *
 * ⭐ 严格按 docs/小程序UI设计规范.md 的设计硬约束：
 *   ·顶部绿底「无水印」徽章 —— 兑现承诺的信任点（冷绿 #1B8A5A，不跟主色走暖）
 *   · 清晰度：实线=强制、虚线=可选。720P 实心、1080P 虚线琥珀
 *   · 「免登录上限 720P」诚实告知，避免用户以为技术不行
 *   · 两个虚线按钮并排 = 视觉权重相同，用户自由选
 *   · 保存按钮在广告位**上方** —— 先满足需求，再要求看广告
 *   · 本页只有 Banner，无插屏无开屏（插屏会打断「保存」这个动作）
 */
const api = require('../../utils/api.js');
const { ParseResult } = require('../../utils/parse-result.js');
const { QUOTA } = require('../../utils/quota.js');
const saver = require('../../utils/saver.js');
const themeUtil = require('../../utils/themes.js');

Page({
  data: {
    theme: 'classic',
    loading: true,
    r: null,          // ParseResult 实例
    title: '',
    authorLine: '',
    cover: '',
    coverRaw: '',     // 原始封面地址（代理加载失败时回退用）
    bgmShow: false,
    bgmLine: '',
    bgmUrl: '',
    bgmPlaying: false,
    isVideo: false,
    isImage: false,
    notices: [],
    titleHint: '',
    statsLine: [],
    tags: [],
    images: [],
    copyText: '',
    copyTags: [],
    options: [],
    selectedIdx: -1,
    freeMaxHeight: 720,
    saving: false,
    savingSub: false,
    savedCount: 0,
    quotaLeft: 0,
    quotaTotal: 0,
    errMsg: ''
  },

  onShow() {
    themeUtil.sync(this);
  },

  onLoad() {
    const app = getApp();
    const r = app.globalData.lastResult;

    if (!r || !r.success) {
      this.setData({ loading: false, errMsg: '结果已丢失，请重新解析' });
      return;
    }

    // 默认选推荐档（未超免费上限的最高档）
    const rec = r.recommendedOption;
    const idx = rec ? r.options.findIndex(o => o.url === rec.url) : -1;

    this.setData({
      loading: false,
      r,
      title: r.title || '（无标题）',
      authorLine: [r.authorName, r.durationText].filter(Boolean).join(' · '),
      coverRaw: r.cover || (r.images[0] ? r.images[0].url : ''),
      cover: api.coverProxy(r.cover || (r.images[0] ? r.images[0].url : '')),
      bgmShow: !!r.musicUrl,
      bgmUrl: r.musicUrl || '',
      bgmLine: [r.musicTitle || '原声', r.musicAuthor]
        .filter(Boolean).join(' · '),
      isVideo: r.isVideo,
      isImage: r.isImage,
      // ⭐ 文件大小（2026-10-22，竞品对齐：视频卡右下角显示「时长+大小」）
      fileSizeText: r.fileSizeText || '',
      durationText: r.durationText || '',
      notices: r.notices,
      titleHint: r.titleHint,
      statsLine: r.statsLine,
      tags: r.tags,
      images: r.images,
      // ⭐ 文案卡（双产出第二路径）：description 优先，缺失时降级 title 并标明
      copyText: r.description || '',
      copyTags: r.description ? r.tags : [],
      // 字幕文案卡（YouTube/FB；ytdlp 引擎下发，无则不显示）
      subtitleText: r.subtitleText || '',
      subtitleLang: r.subtitleLang || '',
      subtitleAuto: !!r.subtitleAuto,
      subtitleLen: (r.subtitleText || '').length,
      subtitlePreview: (r.subtitleText || '').slice(0, 300)
        + ((r.subtitleText || '').length > 300 ? '…' : ''),
      options: this.decorateOptions(r.options, r.anonymousMaxHeight),
      selectedIdx: idx,
      freeMaxHeight: r.anonymousMaxHeight,
      assets: this.buildAssets(r)
    });

    this.refreshQuota();
  },

  /**
   * 构建「本次可提取」素材清单（2026-10-22，竞品对齐的核心）
   *
   * ⭐ 竞品是按素材类型横切列出（视频/封面/文案/配音），
   *   我们此前是纵向堆叠——用户得自己拼「哪一步能拿到什么」。
   *
   * ⭐⭐ 只列【真实可用】的素材：
   *   竞品有「配音→搜索视频中相似声音」，那是另一个服务的能力，
   *   我们没有 —— 列出来点了没反应比不列更糟。
   *   同理BGM：没有 musicUrl 就不列，不占位。
   *   「列了就能用」是这张清单唯一的设计前提。
   */
  buildAssets(r) {
    const list = [];

    if (r.isVideo) {
      list.push({
        key: 'video',
        kind: 'video',
        label: '视频',
        acts: [{ key: 'saveVideo', label: '保存到相册', main: true }]
      });
    }

    // 封面：视频有cover 才列。⚠️ 用 coverRaw（原始直链）保存，
    //   不走 coverProxy —— 代理是给display 用的（解决小程序图片域白名单），
    //   保存时也用代理没必要，且代理 URL 里的 query 会被微信再编码一次。
    if (r.cover) {
      list.push({
        key: 'cover',
        kind: 'cover',
        label: '封面',
        acts: [{ key: 'saveCover', label: '保存封面', main: true }]
      });
    } else if (r.images && r.images.length) {
      list.push({
        key: 'images',
        kind: 'cover',
        label: `图片 ${r.images.length} 张`,
        acts: [{ key: 'saveImages', label: '全部保存', main: true }]
      });
    }

    // 文案：标题与正文是两个不同产出，给两个动作而不是合一个
    //   ——用户要「复制标题」时不该被迫拿走整段正文。
    const textActs = [];
    if (r.title) {
      textActs.push({ key: 'copyTitle', label: '复制标题' });
    }
    if (r.copyText || r.description) {
      textActs.push({ key: 'copyCopy', label: '复制文案', main: !r.title });
    }
    if (r.subtitleText) {
      textActs.push({ key: 'copySubtitle', label: '复制字幕' });
    }
    if (textActs.length) {
      list.push({ key: 'text', kind: 'text', label: '文案', acts: textActs });
    }

    if (r.musicUrl) {
      list.push({
        key: 'audio',
        kind: 'audio',
        label: '背景音乐',
        acts: [
          { key: 'toggleBgm', label: '试听', main: true },
          { key: 'copyBgm', label: '复制链接' }
        ]
      });
    }

    return list;
  },

  /**
   * 素材清单动作分发（data-act → 实际方法）
   *
   * 用一张显式映射表而不是直接 this[act]()：
   * 直接调用等于把 WXML 里的字符串当方法名执行，
   * 任何拼写错误都会在运行时才炸，且能调到任意方法。
   */
  onAssetAction(e) {
    const key = (e.currentTarget.dataset.act || '').toString();
    const map = {
      saveVideo: this.onSave,
      saveCover: this.onSaveCover,
      saveImages: this.onSave,
      copyTitle: this.onCopyTitle,
      copyCopy: this.onCopyCopy,
      copySubtitle: this.onCopySubtitle,
      toggleBgm: this.onBgmToggle,
      copyBgm: this.onCopyBgm
    };
    const fn = map[key];
    if (typeof fn === 'function') {
      fn.call(this, e);
    }
  },

  /** 复制标题（竞品「文案」行的动作之一） */
  onCopyTitle() {
    const t = this.data.title;
    if (!t || t === '（无标题）') {
      wx.showToast({ title: '这条没有标题', icon: 'none' });
      return;
    }
    saver.copyText(t).then(ok => {
      wx.showToast({ title: ok ? '标题已复制' : '复制失败', icon: ok ? 'success' : 'none' });
    });
  },

  /**
   * 保存封面到相册
   *
   * ⚠️ 配额决策：封面**不扣**保存次数。
   *   配额保护的是「视频下载」（消耗带宽/CDN 流量），封面是几十 KB 的图片，
   *   扣它会让用户为一个小操作付代价，体验上说不通。
   *   若将来流量成为瓶颈，应改成独立的「图片配额」而不是挤占视频配额。
   */
  onSaveCover() {
    const url = this.data.coverRaw || this.data.cover;
    if (!url) {
      wx.showToast({ title: '这条没有封面', icon: 'none' });
      return;
    }
    if (this.data.saving) return;
    this.setData({ saving: true });

    saver.saveImage(url, 'jpg').then(res => {
      this.setData({ saving: false });
      if (res.ok) {
        wx.showToast({ title: '封面已保存', icon: 'success' });
      } else if (res.reason === 'auth') {
        // 权限被拒是【可引导】的：直接告诉用户去设置里开
        wx.showModal({
          title: '需要相册权限',
          content: '保存封面需要写入相册的权限，去设置里开启后即可保存。',
          confirmText: '去设置',
          success: m => { if (m.confirm) wx.openSetting(); }
        });
      } else {
        wx.showToast({ title: '封面保存失败，请重试', icon: 'none' });
      }
    });
  },

  /** 封面代理加载失败（未知域 403/CDN 拒绝）→ 回退原始直链 */
  onCoverErr() {
    if (this.data.cover !== this.data.coverRaw && this.data.coverRaw) {
      this.setData({ cover: this.data.coverRaw });
    }
  },

  /** BGM 试听（单例 InnerAudioContext，切页即停） */
  onBgmToggle() {
    const url = this.data.bgmUrl;
    if (!url) return;
    if (!this._audio) {
      this._audio = wx.createInnerAudioContext();
      this._audio.onEnded(() => this.setData({ bgmPlaying: false }));
      this._audio.onError(() => {
        this.setData({ bgmPlaying: false });
        wx.showToast({ title: '音频加载失败', icon: 'none' });
      });
    }
    if (this.data.bgmPlaying) {
      this._audio.stop();
      this.setData({ bgmPlaying: false });
      return;
    }
    this._audio.src = url;
    this._audio.play();
    this.setData({ bgmPlaying: true });
  },

  onCopyBgm() {
    if (!this.data.bgmUrl) return;
    wx.setClipboardData({
      data: this.data.bgmUrl,
      success: () => wx.showToast({ title: '音频链接已复制', icon: 'none' })
    });
  },

  onUnload() {
    if (this._audio) {
      this._audio.destroy();
      this._audio = null;
    }
  },

  /**
   * 给清晰度选项加展示态
   *
   * ⚠️ 服务端返回的 options 不带 locked 标记 —— 那是客户端该判断的事
   *    （同一份 options，两个客户端可能有不同的免费策略）。
   */
  decorateOptions(options, maxHeight) {
    return (options || []).map((o, i) => ({
      idx: i,
      label: `${o.height || '?'}P`,
      url: o.url,
      locked: (o.height || 0) > maxHeight,
      size: o.size || 0
    }));
  },

  refreshQuota() {
    // P0：服务端权威 —— 先乐观渲染缓存，再静默校准
    const c = QUOTA.cachedQuota();
    this.setData({
      quotaLeft: c.is_member ? -1 : Math.max(0, c.save_left ?? 0),
      quotaTotal: QUOTA.VIDEO_SAVE_PER_DAY
    });
    QUOTA.refresh().then(q => {
      this.setData({
        quotaLeft: q.is_member ? -1 : Math.max(0, q.save_left ?? 0),
        quotaTotal: QUOTA.VIDEO_SAVE_PER_DAY
      });
    });
  },

  // ── 选择清晰度 ──
  onPickOption(e) {
    const idx = Number(e.currentTarget.dataset.idx);
    const opt = this.data.options[idx];
    if (!opt) return;

    if (opt.locked) {
      // 触点①：看广告解锁 1080P
      this.onWatchAdUnlock(opt);
      return;
    }
    this.setData({ selectedIdx: idx });
  },

  /** 触点① · 看广告解锁最高画质（不指定某档） */
  onWatchAdUnlockHighest() {
    const best = this.data.options.find(o => o.locked);
    if (!best) {
      wx.showToast({ title: '当前已是最高画质', icon: 'none' });
      return;
    }
    wx.showModal({
      title: '解锁 ' + best.label,
      content: '看一条广告即可解锁高清画质。\n\n（广告位开发中，先为你保留功能入口）',
      confirmText: '知道了',
      showCancel: false
    });
  },

  /** 触点② · 看广告再存 1 次 */
  onWatchAdExtraSave() {
    wx.showModal({
      title: '今日保存次数已用完',
      content: '看一条广告可再保存 1 次。\n\n（广告位开发中，先为你保留功能入口）',
      confirmText: '知道了',
      showCancel: false
    });
  },

  // ── 保存 ──
  async onSave() {
    if (this.data.saving) return;

    const r = this.data.r;
    if (!r) return;

    // 配额闸门（免费用户每日 2 次）
    // ⭐ P0：服务端权威 —— 本地缓存只作乐观显示
    const q = QUOTA.cachedQuota();
    if (!q.is_member && (q.save_left ?? 0) <= 0) {
      this.onWatchAdExtraSave();
      return;
    }

    if (r.isImage) {
      this.saveImages(r);
      return;
    }
    this.saveVideo(r);
  },

  /** 图集：逐张保存（不打包 zip —— 要服务器 CPU，且用户只想存 1~2 张） */
  saveImages(r) {
    const urls = r.images.map(i => i.url).filter(Boolean);
    if (!urls.length) {
      wx.showToast({ title: '没有可保存的图片', icon: 'none' });
      return;
    }

    this.setData({ saving: true });
    const total = urls.length;
    let done = 0;
    let failed = 0;

    // ⛔ wx.downloadFile **不返回 Promise**，它靠 success/fail 回调。
    //   早期版本写Promise.all(requests).then(...) —— 数组里全是请求对象，
    //   Promise.all 会立刻 resolve(undefined)，导致：
    //     · 永远走不到成功提示
    //     · 配额永远不扣（用户无限保存）
    //   必须自己把回调包成 Promise。
    const task = urls.map((url, i) => new Promise(resolve => {
      wx.downloadFile({
        url,
        filePath: `cb_img_${Date.now()}_${i}.jpg`,
        success: res => {
          if (res.statusCode === 200) done++;
          else failed++;
          resolve();
        },
        fail: () => { failed++; resolve(); }
      });
    }));

    Promise.all(task).then(() => {
      this.setData({ saving: false });
      if (done === 0) {
        wx.showToast({ title: '保存失败，请检查网络', icon: 'none' });
        return;
      }
      const ok = failed === 0;
      saver.afterSaved(1);
      this.refreshQuota();
      wx.showModal({
        title: ok ? '已保存' : '部分成功',
        content: ok
          ? `${total} 张图片已保存到相册`
          : `${done} 张成功，${failed} 张失败（CDN 可能有访问限制）`,
        showCancel: false
      });
    });
  },

  /** 视频：下载后调起保存到相册 */
  saveVideo(r) {
    const opt = this.data.options[this.data.selectedIdx];
    const url = (opt && opt.url) || r.videoUrl;
    if (!url) {
      wx.showToast({ title: '没有可保存的地址', icon: 'none' });
      return;
    }

    // AcFun 只有 m3u8，必须服务端合并 —— 不能直接下载
    if (r.mergeRequired) {
      wx.showToast({ title: '该平台需服务端合并，请稍候', icon: 'none', duration: 2500 });
      return;
    }

    this.setData({ saving: true });
    wx.showLoading({ title: '保存中…', mask: true });

    wx.downloadFile({
      url,
      filePath: `cb_video_${Date.now()}.mp4`,
      success: res => {
        wx.hideLoading();
        this.setData({ saving: false });
        if (res.statusCode !== 200) {
          wx.showToast({ title: '下载失败', icon: 'none' });
          return;
        }
        // 保存到相册（小程序原生能力，无需权限申请）
        wx.saveVideoToPhotosAlbum({
          filePath: res.tempFilePath,
          success: () => {
            saver.afterSaved(1);
            this.refreshQuota();
            wx.showToast({ title: '已保存到相册', icon: 'success' });
          },
          fail: err => {
            if (/auth|deny|permission/i.test(err.errMsg || '')) {
              wx.showModal({
                title: '需要相册权限',
                content: '首次保存需要你授权「保存到相册」，去设置里打开即可。',
                confirmText: '去设置',
                success: r2 => {
                  if (r2.confirm) wx.openSetting();
                }
              });
            } else {
              wx.showToast({ title: '保存失败', icon: 'none' });
            }
          }
        });
      },
      fail: () => {
        wx.hideLoading();
        this.setData({ saving: false });
        wx.showToast({ title: '下载失败，请检查网络', icon: 'none' });
      }
    });
  },

  /** 图片预览 */
  onPreviewImage(e) {
    const urls = this.data.images.map(i => i.url);
    wx.previewImage({ current: e.currentTarget.dataset.src, urls });
  },

  /** 视频预览（走video 组件指向 CDN，零流量成本） */
  onVideoPlay() {
    const opt = this.data.options[this.data.selectedIdx];
    const url = (opt && opt.url) || (this.data.r && this.data.r.videoUrl);
    if (!url) return;
    wx.previewMedia({
      sources: [{ url, type: 'video' }],
      fail: () => {
        // 有些 CDN 不支持 previewMedia，退回复制地址
        wx.setClipboardData({
          data: url,
          success: () => wx.showToast({ title: '地址已复制，可在浏览器打开', icon: 'none' })
        });
      }
    });
  },

  /** 复制文案全文（双产出第二路径） */
  onCopyCopy() {
    const text = this.data.copyText;
    if (!text) return;
    saver.copyText(text).then(ok => {
      wx.showToast({ title: ok ? '文案已复制' : '复制失败', icon: ok ? 'success' : 'none' });
    });
  },

  /** 复制字幕全文（YouTube/FB 视频转文案） */
  onCopySubtitle() {
    const text = this.data.subtitleText;
    if (!text) return;
    saver.copyText(text).then(ok => {
      wx.showToast({ title: ok ? '字幕已复制' : '复制失败', icon: ok ? 'success' : 'none' });
    });
  },

  /** 字幕存入云素材库（文案库分类）——衔接违禁词检测闭环 */
  async onSaveSubtitle() {
    const r = this.data.r;
    const text = this.data.subtitleText;
    if (!r || !text) return;
    if (this.data.savingSub) return;
    this.setData({ savingSub: true });
    try {
      const openid = await QUOTA.ensureLogin();
      if (openid.startsWith('offline_')) {
        wx.showToast({ title: '需要连接解析服务', icon: 'none' });
        return;
      }
      const resp = await api.libraryAdd(openid, {
        item_type: 'copy',
        title: (r.title || 'YouTube 字幕').slice(0, 60),
        platform: r.platform || '',
        author: r.authorName || '',
        cover: r.cover || '',
        source_text: text
      });
      if (resp && resp.ok) {
        saver.afterSaved(1);
        wx.showToast({ title: '已存入文案库', icon: 'success' });
      } else {
        wx.showToast({ title: '保存失败，请重试', icon: 'none' });
      }
    } catch (e) {
      wx.showToast({ title: '连不上解析服务', icon: 'none' });
    } finally {
      this.setData({ savingSub: false });
    }
  },

  /** Banner 广告占位（⏳ 待接入） */
  onAdTap() {
    wx.showToast({ title: '广告位开发中', icon: 'none' });
  },

  navHome() {
    wx.switchTab({ url: '/pages/index/index' });
  },

  navMember() {
    wx.navigateTo({ url: '/pages/member/member' });
  },

  onShareAppMessage() {
    const r = this.data.r;
    return {
      title: r ? r.title || '素材解析' : '素材解析',
      path: '/pages/index/index'
    };
  }
});
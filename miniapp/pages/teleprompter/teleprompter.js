/**
 * 提词器（P2 · 2026-10-07 上线）
 *
 * 场景：自媒体口播拍摄——手机架在镜头前滚动台词，边看边念。
 * 纯前端工具：无网络请求、无内容抓取、无配额消耗（合规零风险）。
 *
 * 交互：
 *   · 编辑态：粘贴台词 → 调速度（3 档）/ 字号（3 档）→ 开始
 *   · 播放态：全屏黑底大字滚动（30ms 步进平滑滚动）
 *     · 点屏幕 = 暂停/继续；底部 = 速度即时调 + 退出
 *     · 滚到底自动停止（不假循环）
 */
const themeUtil = require('../../utils/themes.js');

const SPEED_MAP = { 1: 0.5, 2: 1, 3: 2 };       // 档位 → 每帧像素系数
const FONT_MAP = { 1: 34, 2: 44, 3: 58 };        // 档位 → rpx 字号

Page({
  data: {
    theme: 'classic',
    script: '',
    playing: false,          // 播放态（全屏滚动）
    paused: false,
    speed: 2,                // 档位 1-3
    fontSize: 2,             // 档位 1-3
    scrollTop: 0,
    errMsg: ''
  },

  onShow() {
    themeUtil.sync(this);
  },

  onHide() {
    this._stop();            // 切页自动停，防后台耗电
  },

  onUnload() {
    this._stop();
  },

  onInput(e) {
    this.setData({ script: e.detail.value || '', errMsg: '' });
  },

  setSpeed(e) {
    this.setData({ speed: Number(e.currentTarget.dataset.v) || 2 });
  },

  setFont(e) {
    this.setData({ fontSize: Number(e.currentTarget.dataset.v) || 2 });
  },

  /** 开始播放：非空校验 → 滚动到内容区顶 → 启动计时器 */
  start() {
    const text = (this.data.script || '').trim();
    if (!text) {
      this.setData({ errMsg: '请先输入或粘贴台词' });
      return;
    }
    this.setData({ playing: true, paused: false, scrollTop: 0, errMsg: '' });
    this._launch();
  },

  _launch() {
    this._stop();
    const step = SPEED_MAP[this.data.speed] || 1;
    this._timer = setInterval(() => {
      // scroll-top 单位 px；rpx 字号换算系数近似 0.5（750 设计稿）
      const next = this.data.scrollTop + step;
      this.setData({ scrollTop: next });
      wx.createSelectorQuery().in(this)
        .select('#tpBody').boundingClientRect(rect => {
          const scroller = this._viewportH || 0;
          if (rect && scroller && rect.top + rect.height < scroller) {
            this._stopScroll();            // 滚到底自动停
            this.setData({ paused: true });
          }
        }).exec();
    }, 30);
  },

  _stopScroll() {
    this._timer && clearInterval(this._timer);
    this._timer = null;
  },

  _stop() {
    this._stopScroll();
  },

  /** 播放态：点屏幕 暂停/继续 */
  toggle() {
    if (this.data.paused) {
      this.setData({ paused: false });
      this._launch();
    } else {
      this._stopScroll();
      this.setData({ paused: true });
    }
  },

  /** 播放中调速度：即时生效（重启计时器，保持位置） */
  changeSpeed(e) {
    const v = Number(e.currentTarget.dataset.v) || 2;
    this.setData({ speed: v });
    if (!this.data.paused) this._launch();
  },

  exit() {
    this._stop();
    this.setData({ playing: false, paused: false, scrollTop: 0 });
  },

  /** 播放区高度测量（滚到底判定用） */
  onViewportReady() {
    wx.createSelectorQuery().in(this)
      .select('#tpScroll').boundingClientRect(rect => {
        this._viewportH = rect ? rect.height : 0;
      }).exec();
  }
});

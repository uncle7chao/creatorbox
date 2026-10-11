/**
 * CreatorBox 小程序入口
 *
 * 全局状态用 globalData 而非状态库：
 * 本期数据流极浅（首页 → 结果页 → 分享），引入状态库是过度设计。
 * 待接入会员体系/云端同步后再评估。
 */
App({
  globalData: {
    /** 最近一次解析结果（ParseResult 实例） */
    lastResult: null,
    /** 最近一次输入原文（链接或分享文案） */
    lastInputText: '',
    /** 从素材库点「重新解析」带过来的链接 */
    pendingInput: ''
  },

  onLaunch() {
    // 首次启动时初始化配额日期，避免跨天判断失效
    try {
      wx.setStorageSync('cb_saved_date', new Date().toDateString());
      wx.setStorageSync('cb_saved_count', 0);
    } catch (e) {
      // 存储不可用不阻塞启动
    }
    // 皮肤：启动即恢复上次选择（导航/tabBar 由各页 onShow 的 sync 处理）
    try {
      this.globalData.theme =
        require('./utils/themes.js').current();
    } catch (e) { /* 主题加载失败用默认 */ }
  },

  onShow(options) {
    // ⏳ 分享接收通道（M0-V1 探针验证后再接）
    //   平台自定义 scheme 可能走私有通道而不触发 onShareAppMessage，
    //   未验证前不做，避免白做。
    if (options && options.query && options.query.scene) {
      this.globalData.pendingInput = decodeURIComponent(options.query.scene);
    }
  },

  onError(err) {
    // 生产环境应上报监控；本期先写日志，不静默吞掉
    console.error('[CreatorBox] 未捕获异常:', err);
  }
});
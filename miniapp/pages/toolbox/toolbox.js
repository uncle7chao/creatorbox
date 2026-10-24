/**
 * 工具箱页（P0，2026-10-07）
 *
 * 分区：可用工具（4 项真实）+ 即将上线（8 项占位卡）
 *
 * ⭐ 占位卡规则（2026-10-07 用户拍板「展示不开发」）：
 *   · 置灰 + 虚线边框 + 锁形角标 +「规划中」胶囊
 *   · 点击只弹「功能规划中」—— 不跳转、不收集手机号（合规：诱导留资是红线）
 *   · 底部免责小字闭环
 */
const api = require('../../utils/api.js');
const themeUtil = require('../../utils/themes.js');

Page({
  data: {
    theme: 'classic',
    live: api.TOOLBOX_LIVE,
    placeholders: api.TOOLBOX_PLACEHOLDERS,
    platformCount: 8
  },

  onShow() {
    themeUtil.sync(this);
  },

  onLoad() {
    api.health().then(h => {
      if (h && h.platforms) this.setData({ platformCount: h.platforms.length });
    }).catch(() => { });
  },

  onLive(e) {
    const type = e.currentTarget.dataset.type;
    switch (type) {
      case 'parse':
        wx.switchTab({ url: '/pages/index/index' });
        break;
      case 'batch':
        wx.navigateTo({ url: '/pages/batch/batch' });
        break;
      case 'copy':
        // 文案提取 = 首页输入后的第二产出 —— 回首页提示粘贴
        wx.switchTab({ url: '/pages/index/index' });
        break;
      case 'rank':
        // M1.5：榜单已上线（B站热榜）
        wx.switchTab({ url: '/pages/ranking/ranking' });
        break;
      case 'banned':
        // 2026-10-09 违禁词检测：发布前合规自检（免费 3 次/日，会员不限）
        wx.navigateTo({ url: '/pages/banned/banned' });
        break;
      case 'column':
        // M1.5：内容专栏（静态页方案，零服务端依赖）
        wx.navigateTo({ url: '/pages/column/column' });
        break;
      case 'teleprompter':
        // P2 提词器：纯前端工具，无配额无网络
        wx.navigateTo({ url: '/pages/teleprompter/teleprompter' });
        break;
      case 'pdftool':
        // P2 PDF 三件：合并/提取页/加水印（pypdf，服务端处理）
        wx.navigateTo({ url: '/pages/pdftool/pdftool' });
        break;
      default:
        wx.showToast({ title: '功能规划中', icon: 'none' });
    }
  },

  onPlaceholder(e) {
    // ⭐ 两种占位要分开（2026-10-24）：
    //   ① 规划中 → 只吐一个 toast（合规：不跳转、不收集联系方式，诱导留资是审核红线）
    //   ② PC / App 专用 → 明确告知去哪用。这类功能**不是没做，是不在小程序做**
    //      （AI 创作属深度合成类目，个人主体过不了审），说清楚比含糊更好。
    // ⚠️ dataset 里的布尔值到 JS 会变成字符串 'true'，不能只判 === true
    const pcOnly = e.currentTarget.dataset.pc === true ||
                   e.currentTarget.dataset.pc === 'true';
    if (pcOnly) {
      wx.showModal({
        title: '请在电脑端使用',
        content: '文案创作需要键盘输入和长文本编辑，请到 PC 或 App 端使用。',
        showCancel: false,
        confirmText: '知道了'
      });
      return;
    }
    wx.showToast({ title: '该功能在规划中，敬请期待', icon: 'none' });
  }
});
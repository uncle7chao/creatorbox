/**
 * 合规页（免责 + 协议 + 举报入口 + 投诉渠道）
 *
 * ⭐ 规范 3.13 硬要求：必须提供投诉与举报渠道，且可达。
 *
 * ⚠️ 去水印类小程序是下架重灾区（行业趋势：平台已能 AI 识别水印擦除行为）。
 *    这一页不是「装饰」——它是合规审核时的必要材料，也是被驳回时的申辩依据。
 *    内容按《微信小程序运营规范》4.3「不为违法行为提供便利」的口径写。
 *
 * ⏳ 正式上线前需替换：真实主体名称、备案号、投诉邮箱、受理时限。
 *    现在写的是占位文案，不能直接提审。
 */
const CONTACT_EMAIL = 'complaint@creatorbox.example';   // TODO 上线前替换
const REPORT_PHONE = '';// TODO 上线前填真实号码

const themeUtil = require('../../utils/themes.js');

Page({
  data: {
    theme: 'classic',
    version: '1.0.0',
    email: CONTACT_EMAIL,
    hasPhone: !!REPORT_PHONE
  },

  onShow() {
    themeUtil.sync(this);
  },

  onCopyEmail() {
    wx.setClipboardData({
      data: CONTACT_EMAIL,
      success: () => wx.showToast({ title: '邮箱已复制', icon: 'none' })
    });
  },

  onCallPhone() {
    if (!REPORT_PHONE) {
      wx.showToast({ title: '联系电话待上线前补充', icon: 'none' });
      return;
    }
    wx.makePhoneCall({ phoneNumber: REPORT_PHONE });
  },

  /** 在微信内举报：引导用户走官方渠道（这是平台要求的路径） */
  onReport() {
    wx.showModal({
      title: '投诉与举报',
      content: '如发现本小程序违规内容，可通过以下方式反馈：\n' +
               '· 在右上角「···」→ 投诉（微信官方渠道）\n' +
               `· 发送邮件至${CONTACT_EMAIL}\n\n` +
               '我们将在 7 个工作日内核查并回复。',
      confirmText: '复制邮箱',
      cancelText: '关闭',
      success: res => {
        if (res.confirm) {
          wx.setClipboardData({
            data: CONTACT_EMAIL,
            success: () => wx.showToast({ title: '邮箱已复制', icon: 'none' })
          });
        }
      }
    });
  }
});
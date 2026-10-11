/**
 * 积分中心（P2 · 2026-10-08）
 *
 * 玩法闭环：每日签到 +10（连签 7 天额外 +20）→ 100 积分 = 1 天会员体验
 * → 会员时间写 users.member_until（服务端权威），体验后转付费。
 *
 * 诚实原则：
 *   · 签到幂等由服务端 UNIQUE(openid,day) 保证，本地不预写
 *   · 余额 = 服务端流水累加，客户端只展示不记账
 */
const api = require('../../utils/api.js');
const themeUtil = require('../../utils/themes.js');

Page({
  data: {
    theme: 'classic',
    balance: 0,
    streak: 0,
    days: [],                // 近 7 天签到日期
    signedToday: false,
    message: '',
    redeemCost: 100,
    redeemableDays: 0,
    member: null,            // 兑换后的会员状态
    busy: false,
    errMsg: ''
  },

  async onShow() {
    themeUtil.sync(this);
    await this.refresh();
  },

  async refresh() {
    try {
      const openid = wx.getStorageSync('cb_openid') || '';
      if (!openid) return;
      const r = await api.points(openid);
      if (r && r.ok) {
        const signedToday = (r.days || []).includes(this._today());
        this.setData({
          balance: r.balance, streak: r.streak, days: r.days || [],
          signedToday, redeemCost: r.redeem_cost || 100,
          redeemableDays: Math.floor((r.balance || 0) / (r.redeem_cost || 100))
        });
      }
    } catch (e) { /* 静默：服务未连时页面可用 */ }
  },

  _today() {
    const d = new Date();
    const p = n => (n < 10 ? '0' + n : '' + n);
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
  },

  async onSign() {
    if (this.data.busy || this.data.signedToday) return;
    this.setData({ busy: true });
    try {
      const openid = wx.getStorageSync('cb_openid') || '';
      const r = await api.pointsSign(openid);
      this.setData({
        balance: r.balance, streak: r.streak, days: r.days || [],
        signedToday: true, message: r.message || `+${r.gained || 10} 积分`,
        redeemableDays: Math.floor((r.balance || 0) / (r.redeem_cost || 100))
      });
      wx.showToast({ title: r.message || '签到成功', icon: 'none' });
    } catch (e) {
      this.setData({ errMsg: e.message || '签到失败' });
    } finally {
      this.setData({ busy: false });
    }
  },

  async onRedeem() {
    if (this.data.busy || this.data.redeemableDays < 1) return;
    wx.showModal({
      title: '兑换会员',
      content: `用 ${this.data.redeemableDays * this.data.redeemCost} 积分兑换 ` +
               `${this.data.redeemableDays} 天会员体验？立即生效。`,
      success: async res => {
        if (!res.confirm) return;
        this.setData({ busy: true });
        try {
          const openid = wx.getStorageSync('cb_openid') || '';
          const r = await api.pointsRedeem(openid);
          this.setData({
            balance: r.balance, days: r.days || [],
            redeemableDays: Math.floor((r.balance || 0) / (r.redeem_cost || 100)),
            member: r.member,
            message: `兑换成功：会员 +${r.redeemed_days} 天`
          });
          wx.showToast({ title: `会员 +${r.redeemed_days} 天`, icon: 'none' });
        } catch (e) {
          this.setData({ errMsg: e.message || '兑换失败' });
        } finally {
          this.setData({ busy: false });
        }
      }
    });
  },

  goMember() {
    wx.switchTab({ url: '/pages/member/member' });
  }
});

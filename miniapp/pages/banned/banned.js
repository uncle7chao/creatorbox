/**
 * 违禁词检测（2026-10-09，工具矩阵第 8 个真实工具）
 *
 * 定位：发布前合规自检 —— 解析拿素材 → 存文案库 → 这里查一遍 → 放心发布。
 * 免费：3 次/日，只查基础词库（广告法极限词 + 诱导互动）
 * 会员：不限次 + 全类目（医疗/金融/导流/虚假夸大）
 *
 * ⚠️ 合规口径（页面必透传）：检测结果 = 风险提示，不是法律意见。
 */
const api = require('../../utils/api.js');
const { QUOTA } = require('../../utils/quota.js');
const themeUtil = require('../../utils/themes.js');

Page({
  data: {
    theme: 'classic',
    text: '',
    checking: false,

    checked: false,        // 是否已出过结果
    riskLevel: 'clean',    // clean / medium / high
    total: 0,
    segments: [],          // [{t, hit}] 原文标红分段
    groups: [],            // [{category, name, risk, count, words:[{word,count,suggest}]}]
    locked: [],            // 被会员门槛锁住的类目名（升级引导）
    isMember: false,
    used: 0,
    limit: 3
  },

  onShow() {
    themeUtil.sync(this);
    this.setData({ isMember: QUOTA.isMember() });
  },

  onInput(e) {
    this.setData({ text: e.detail.value });
  },

  clearInput() {
    this.setData({
      text: '', checked: false, riskLevel: 'clean', total: 0,
      segments: [], groups: [], locked: []
    });
  },

  onPaste() {
    wx.getClipboardData({
      success: (r) => {
        if (r.data && r.data.trim()) {
          this.setData({ text: r.data.trim() });
        }
      }
    });
  },

  onCheck() {
    const text = (this.data.text || '').trim();
    if (!text) {
      wx.showToast({ title: '先粘贴要检测的文案', icon: 'none' });
      return;
    }
    if (this.data.checking) return;
    this.setData({ checking: true });
    wx.showLoading({ title: '检测中…', mask: true });

    QUOTA.ensureLogin().then(openid => {
      if (openid.startsWith('offline_')) {
        wx.hideLoading();
        this.setData({ checking: false });
        wx.showModal({
          title: '网络不可用',
          content: '检测需要连接解析服务，请确认服务已启动。',
          showCancel: false
        });
        return;
      }
      api.bannedCheck(openid, text).then(r => {
        wx.hideLoading();
        this.setData({ checking: false });
        if (!r) {
          wx.showToast({ title: '连接失败，请重试', icon: 'none' });
          return;
        }
        if (r.ok) {
          this.setData({
            checked: true,
            riskLevel: r.risk_level,
            total: r.total,
            segments: r.segments || [],
            groups: r.groups || [],
            locked: r.locked || [],
            isMember: !!r.is_member,
            used: r.quota ? r.quota.used : 0,
            limit: r.quota ? r.quota.limit : 3
          });
        } else if (r.reason === 'quota_exhausted') {
          this.setData({
            used: r.quota ? r.quota.used : 3,
            limit: r.quota ? r.quota.limit : 3
          });
          wx.showModal({
            title: '今日免费次数已用完',
            content: r.message || '免费用户每日 3 次。开通会员不限次，并解锁医疗/金融/导流等全类目词库。',
            confirmText: '开通会员',
            cancelText: '明天再来',
            success: (res) => {
              if (res.confirm) {
                wx.switchTab({ url: '/pages/member/member' });
              }
            }
          });
        } else {
          wx.showToast({ title: r.message || '检测失败，请重试', icon: 'none' });
        }
      }).catch(() => {
        wx.hideLoading();
        this.setData({ checking: false });
        wx.showModal({
          title: '连接失败',
          content: '连不上解析服务，请确认服务已启动后重试。',
          showCancel: false
        });
      });
    });
  },

  onUpgrade() {
    wx.switchTab({ url: '/pages/member/member' });
  },

  /** 一键复制干净版文案（把命中词按替换建议修正后复制） */
  onCopyClean() {
    let out = this.data.text || '';
    const pairs = [];
    (this.data.groups || []).forEach(g => {
      (g.words || []).forEach(w => {
        if (w.suggest) pairs.push([w.word, w.suggest]);
      });
    });
    // 长词先替换，避免短词先替换破坏长词匹配
    pairs.sort((a, b) => b[0].length - a[0].length);
    pairs.forEach(([w, s]) => { out = out.split(w).join(s); });
    if (!pairs.length) {
      wx.showToast({ title: '没有可自动替换的词', icon: 'none' });
      return;
    }
    wx.setClipboardData({
      data: out,
      success: () => wx.showToast({ title: '修正版已复制', icon: 'none' })
    });
  }
});

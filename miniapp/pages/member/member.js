/**
 * 屏 3 · 会员页
 *
 * ⭐ 规范里的 5 条设计硬约束（决定 9.9 卖不卖得动）：
 *   ① 免费区在**上**，会员区在下 —— 先给用户「我够用吗」的判断依据
 *   ② 会员区用绿色卡片包围 —— 视觉上「这块是解开的」
 *   ③ 批量解析是核心卖点，但在对比里才显得有价值
 *   ④ ⛔ 不写划线价 ¥19.9 —— 从来没有 19.9，写了是虚假原价被投诉
 *   ⑤ 必写「不自动续费」—— 9.9 无年费的必要说明，降低决策门槛
 *
 * ⏳ 支付未接入（需先跑通小程序审核 +开通微信支付）。
 *    当前页面的付费按钮给明确提示，不假装能买。
 */
const { QUOTA } = require('../../utils/quota.js');
const api = require('../../utils/api.js');
const themeUtil = require('../../utils/themes.js');

Page({
  data: {
    theme: 'classic',
    themeList: themeUtil.THEMES_KEYS.map(k => ({
      key: k, name: themeUtil.THEMES[k].name
    })),
    price: 9.9,
    freeLimit: QUOTA.VIDEO_SAVE_PER_DAY,
    // 会员特权网格（参考竞品「更多免费工具」卡式：图标+名+副标）
    perks: [
      { name: '批量解析', desc: '单次 10 条', cls: 'batch' },
      { name: '高清画质', desc: '最高 1080P', cls: 'hd' },
      { name: '保存不限次', desc: '每日上限解除', cls: 'save' },
      { name: '云端素材库', desc: '多设备同步', cls: 'cloud' },
      { name: '新功能优先', desc: '抢先体验', cls: 'fast' }
    ],
    freeBenefits: [],
    memberBenefits: [],
    isMember: false
  },

  onLoad() {
    this.setData({
      freeBenefits: QUOTA.freeBenefits(),
      memberBenefits: QUOTA.memberBenefits()
    });
  },

  onShow() {
    themeUtil.sync(this);
    this.setData({
      isMember: QUOTA.isMember(),
      theme: themeUtil.current()
    });
  },

  /** 皮肤切换：落库 + tabBar/导航实时换色 + 当前页立即应用 */
  onPickTheme(e) {
    const key = e.currentTarget.dataset.key;
    if (!key) return;
    themeUtil.setTheme(key);
    this.setData({ theme: key });
    wx.showToast({ title: '已切换', icon: 'none' });
  },

  onBuy() {
    if (this.data.isMember) return;
    // ⏳ 微信支付未接（游客 AppID 无法开通商户号）。
    //    购买闭环当前走卡密：线下收款 → 发码 → 输码开通（服务端 member_add_days）。
    wx.showModal({
      title: '开通会员',
      content: '当前通过「卡密兑换」开通：向工作室购买卡密后输入即可。是否输入卡密？',
      confirmText: '输入卡密',
      cancelText: '再想想',
      success: (res) => {
        if (res.confirm) this.onRedeemCode();
      }
    });
  },

  /** 跨端绑定确认端（v4 §2.4）：输入 App/PC 端生成的 6 位桥接码，
   *  把该设备身份绑到当前账号 → 电脑/App 同账号同会员。
   *  错误语义来自服务端 detail，逐项翻译成用户话术。 */
  onBridgeBind() {
    QUOTA.ensureLogin().then(openid => {
      if (openid.startsWith('offline_')) {
        wx.showModal({
          title: '网络不可用',
          content: '跨端绑定需要连接解析服务，请检查服务是否已启动。',
          showCancel: false
        });
        return;
      }
      wx.showModal({
        title: '跨端绑定',
        content: '输入电脑 / App 端显示的 6 位绑定码',
        editable: true,
        placeholderText: '6 位数字',
        confirmText: '绑定',
        cancelText: '取消',
        success: (res) => {
          if (!res.confirm) return;
          const code = (res.content || '').trim();
          if (!/^\d{6}$/.test(code)) {
            wx.showToast({ title: '请输入 6 位数字绑定码', icon: 'none' });
            return;
          }
          wx.showLoading({ title: '绑定中…', mask: true });
          api.bridgeConfirm(openid, code).then(({ statusCode, data }) => {
            wx.hideLoading();
            if (statusCode === 200 && data && data.ok) {
              wx.showModal({
                title: '绑定成功',
                content: '该设备已登录同一账号：\n会员与素材库将自动同步',
                showCancel: false,
                confirmText: '好的'
              });
            } else {
              const REASON = {
                code_not_found: '绑定码不存在，请在电脑 / App 端重新生成',
                code_expired: '绑定码已过期（5 分钟有效），请重新生成',
                code_locked: '尝试次数过多，该码已锁定，请重新生成',
                identity_taken: '该设备已绑定其他账号，如需换绑请先在原设备解除',
                need_openid: '登录态异常，请重新进入本页重试',
                user_not_found: '登录态异常，请重新进入本页重试'
              };
              wx.showModal({
                title: '绑定失败',
                content: REASON[(data && data.detail)] || '绑定失败，请稍后重试',
                showCancel: false
              });
            }
          }).catch(() => {
            wx.hideLoading();
            wx.showModal({
              title: '连接失败',
              content: '连不上解析服务，请确认服务已启动后重试。',
              showCancel: false
            });
          });
        }
      });
    });
  },

  /** 卡密兑换：ensureLogin → 弹输入框 → 服务端核销 + 顺延会员天数 */
  onRedeemCode() {
    QUOTA.ensureLogin().then(openid => {
      if (openid.startsWith('offline_')) {
        wx.showModal({
          title: '网络不可用',
          content: '卡密兑换需要连接解析服务，请检查服务是否已启动。',
          showCancel: false
        });
        return;
      }
      wx.showModal({
        title: '卡密兑换',
        content: '输入购买获得的卡密（形如 CBXXXX-XXXX-XXXX）',
        editable: true,
        placeholderText: 'CBXXXX-XXXX-XXXX',
        confirmText: '兑换',
        cancelText: '取消',
        success: (res) => {
          if (!res.confirm) return;
          const code = (res.content || '').trim();
          if (!code) {
            wx.showToast({ title: '请输入卡密', icon: 'none' });
            return;
          }
          wx.showLoading({ title: '兑换中…', mask: true });
          api.redeemCode(openid, code).then(r => {
            wx.hideLoading();
            if (r && r.ok) {
              const d = new Date((r.member.expire_at || 0) * 1000);
              const p = n => (n < 10 ? '0' : '') + n;
              const expireText = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
              this.setData({ isMember: true });
              QUOTA.refresh();
              wx.showModal({
                title: '兑换成功',
                content: `会员已开通 +${r.days} 天\n有效期至 ${expireText}`,
                showCancel: false,
                confirmText: '太好了'
              });
            } else {
              wx.showModal({
                title: '兑换失败',
                content: (r && r.error) || '卡密无效，请核对后重试',
                showCancel: false
              });
            }
          }).catch(() => {
            wx.hideLoading();
            wx.showModal({
              title: '连接失败',
              content: '连不上解析服务，请确认服务已启动后重试。',
              showCancel: false
            });
          });
        }
      });
    });
  },

  onRestore() {
    // 支付未接：恢复购买 = 重新输入卡密（换设备/清缓存后会员身份找回走同一服务端记录）
    wx.showModal({
      title: '恢复购买',
      content: '会员记录在服务端，同一身份自动恢复；换设备可用卡密重新兑换。',
      confirmText: '输入卡密',
      cancelText: '知道了',
      success: (res) => {
        if (res.confirm) this.onRedeemCode();
      }
    });
  },

  /** 我的功能列表导航 */
  navLibrary() {
    wx.switchTab({ url: '/pages/library/library' });
  },

  navRanking() {
    wx.switchTab({ url: '/pages/ranking/ranking' });
  },

  navPoints() {
    wx.navigateTo({ url: '/pages/points/points' });
  },

  onOrders() {
    // 会员支付未接（卡 ICP 备案+商户号）—— 诚实占位，不假数据
    wx.showModal({
      title: '订单记录',
      content: '微信支付开放后将在此展示订单与会员到期时间',
      showCancel: false,
      confirmText: '知道了'
    });
  },

  navCompliance() {
    wx.navigateTo({ url: '/pages/compliance/compliance' });
  },

  // ── 注销账号（隐私保护指引 §四）──
  // 流程：预览将删除什么 → wxModal 二次确认 → 调接口 → 清本地缓存回首页。
  // ⭐ 不可逆操作，双重确认缺一不可：这里 confirm 一次，接口 confirm 字段再校验一次。
  onPurgePreview() {
    const openid = wx.getStorageSync('openid');
    if (!openid) {
      wx.showToast({ title: '未登录', icon: 'none' });
      return;
    }
    wx.showLoading({ title: '查询中' });
    api.purgePreview(openid)
      .then(data => {
        wx.hideLoading();
        if (!data || data.unknown_user) {
          wx.showModal({
            title: '账号注销',
            content: '未找到你的账号数据，可能已注销或已清除。',
            showCancel: false
          });
          return;
        }
        const c = data.counts || {};
        const items = [
          ['素材库条目', c.library_items],
          ['配额记录', c.quota_daily],
          ['签到记录', c.points_sign],
          ['跨端绑定身份', c.identities],
          ['登录凭证', c.auth_tokens]
        ].filter(x => x[1] > 0)
         .map(x => `· ${x[0]}：${x[1]} 条`).join('\n') || '· 无';

        wx.showModal({
          title: '确认注销账号？',
          content: `将删除以下数据：\n${items}\n\n` +
                   `此操作【不可恢复】，且会同时退出 App/电脑端登录。\n` +
                   `平台运营数据（卡密库、违禁词库）不受影响。`,
          confirmText: '确认注销',
          confirmColor: '#D92D20',
          cancelText: '再想想',
          success: res => {
            if (!res.confirm) return;
            this._doPurge(openid);
          }
        });
      })
      .catch(err => {
        wx.hideLoading();
        wx.showToast({ title: err.message || '查询失败', icon: 'none' });
      });
  },

  _doPurge(openid) {
    wx.showLoading({ title: '注销中' });
    api.purgeAccount(openid)
      .then(({ statusCode, data }) => {
        wx.hideLoading();
        if (statusCode !== 200 || !data || !data.ok) {
          const msg = (data && data.detail) || '注销失败，请稍后再试';
          wx.showModal({ title: '注销未完成', content: msg, showCancel: false });
          return;
        }
        // 清本地身份缓存，避免下次进来还拿着已注销的 openid
        wx.removeStorageSync('openid');
        wx.removeStorageSync('user');
        wx.removeStorageSync('isMember');
        wx.showToast({ title: '已注销', icon: 'success' });
        setTimeout(() => wx.switchTab({ url: '/pages/index/index' }), 1200);
      })
      .catch(err => {
        wx.hideLoading();
        wx.showToast({ title: err.message || '注销失败', icon: 'none' });
      });
  }
});
/**
 * Banner 轮播组件（M1.5+）
 *
 * · slides 由页面传入（utils/api.js 的 INDEX_BANNERS）
 * · 可见性由服务端广告配置控制（placement 对应 /api/ads/config 的开关）
 * · 自动轮播 4s + 循环 + 原生指示点；点击按 path 类型跳 tab 页或普通页
 */
const ads = require('../../utils/ads.js');

Component({
  properties: {
    placement: { type: String, value: '' },
    banners: { type: Array, value: [] }
  },

  data: {
    on: false,
    slides: []             // 页面默认帧 + 后台自定义图（首帧）
  },

  lifetimes: {
    attached() {
      ads.getPlacement(this.data.placement).then(p => {
        const slides = [];
        // 后台给该位上传了自定义图 → 作为第一帧（支持点击跳转 link）
        if (p.on && p.image) {
          slides.push({ image: p.image, link: p.link, custom: true });
        }
        (this.data.banners || []).forEach(b => slides.push(b));
        this.setData({ on: p.on, slides });
      });
    }
  },

  methods: {
    onBannerTap(e) {
      const { path, tab } = e.currentTarget.dataset;
      if (!path) return;
      if (tab) {
        wx.switchTab({ url: path });
      } else {
        wx.navigateTo({ url: path });
      }
    }
  }
});

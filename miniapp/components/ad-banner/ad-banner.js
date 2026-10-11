/**
 * 广告位 · Banner 组件（v3，2026-10-08：模式二选一 + 多图轮播）
 *
 * 渲染分支（服务端 /api/ads/config 按位配置，模式互斥）：
 *   mode='code'  → 微信流量主 <ad unit-id>（选广告平台就只显示平台的广告）
 *   mode='image' → 自定义图片：1 张静图 / 2~5 张自动轮播（张数由后台决定）
 *                  后台没传图时回退 fallback 帧（首页传入的默认推广卡）
 *                  连 fallback 都没有 → 自营推广卡（会员 9.9）
 *
 * 合规：自绘区域左上角标「推广」角标，明示非内容；
 *   <ad> 组件由微信渲染自带「广告」标识。
 */
const ads = require('../../utils/ads.js');

Component({
  properties: {
    placement: { type: String, value: '' },
    // 兜底帧（首页传 INDEX_BANNERS 结构卡）：后台未传自定义图时展示
    fallback: { type: Array, value: [] }
  },

  data: {
    on: false,
    mode: 'promo',          // promo 自营卡 / wxad 流量主 / image 自定义图 / cards 兜底卡轮播
    images: [],             // 自定义图（1=静图，≥2=轮播）
    unitId: '',
    link: ''
  },

  lifetimes: {
    attached() {
      ads.getPlacement(this.data.placement).then(p => {
        let mode = 'promo';
        if (p.on && p.mode === 'code' && p.unitId) mode = 'wxad';
        else if (p.on && p.mode === 'image' && p.images.length) mode = 'image';
        else if (p.on && (this.data.fallback || []).length) mode = 'cards';
        this.setData({ on: p.on, mode, images: p.images,
                       unitId: p.unitId, link: p.link });
      });
    }
  },

  methods: {
    /** link 跳转（tab 页用 switchTab，普通页 navigateTo） */
    _go(link) {
      if (!link) return;
      const tabs = ['pages/index/index', 'pages/toolbox/toolbox',
        'pages/ranking/ranking', 'pages/library/library', 'pages/member/member'];
      if (tabs.some(t => link.indexOf(t) === 0)) {
        wx.switchTab({ url: link });
      } else {
        wx.navigateTo({ url: link });
      }
    },
    onTap() { this._go(this.data.link); },
    onTapFallback(e) {
      const { path, tab } = e.currentTarget.dataset;
      if (!path) return;
      if (tab) wx.switchTab({ url: path });
      else wx.navigateTo({ url: path });
    },
    goMember() {
      wx.switchTab({ url: '/pages/member/member' });
    },
    /** 上报广告出错（流量主 <ad> 加载失败时静默收起，不留白块） */
    onAdError() {
      this.setData({ on: false });
    }
  }
});

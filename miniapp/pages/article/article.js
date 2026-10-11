/**
 * 运营干货 · 文章详情页（M1.5）
 *
 * 静态数据渲染：id 从专栏列表页传入，utils/articles.js 取内容。
 * 合规：分享不与权益挂钩；文末固定合规提示（内容为方法建议，非收益承诺）。
 */
const { articleById } = require('../../utils/articles.js');
const themeUtil = require('../../utils/themes.js');

Page({
  data: {
    theme: 'classic',
    loaded: false,
    article: null,      // { id, cat, title, summary, minutes, sections:[{h, ps:[]}] }
    notFound: false
  },

  onShow() {
    themeUtil.sync(this);
  },

  onLoad(opts) {
    const a = articleById(opts && opts.id);
    if (!a) {
      this.setData({ notFound: true, loaded: true });
      return;
    }
    this.setData({ article: a, loaded: true });
    wx.setNavigationBarTitle({ title: a.cat });
  },

  navColumn() {
    wx.navigateBack({
      fail: () => wx.navigateTo({ url: '/pages/column/column' })
    });
  },

  onShareAppMessage() {
    const a = this.data.article;
    return {
      title: a ? a.title : '运营干货',
      path: a ? `/pages/article/article?id=${a.id}` : '/pages/column/column'
    };
  }
});

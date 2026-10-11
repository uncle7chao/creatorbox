/**
 * 运营干货 · 专栏列表页（M1.5）
 *
 * 静态页方案：数据来自 utils/articles.js，零服务端依赖。
 * 交互：分类筛选 + 关键词搜索（标题/摘要命中即可）。
 */
const { CATEGORIES, allArticles } = require('../../utils/articles.js');
const themeUtil = require('../../utils/themes.js');

Page({
  data: {
    theme: 'classic',
    categories: CATEGORIES,
    activeCat: '全部',
    kw: '',
    shown: [],          // 过滤后的渲染列表
    total: 0
  },

  onLoad() {
    const all = allArticles();
    this.setData({ shown: all, total: all.length });
  },

  onShow() {
    themeUtil.sync(this);
    // 静态数据无需刷新；预留
  },

  filter() {
    const kw = (this.data.kw || '').trim().toLowerCase();
    const cat = this.data.activeCat;
    const shown = allArticles().filter(a =>
      (cat === '全部' || a.cat === cat) &&
      (!kw || a.title.toLowerCase().includes(kw) ||
        a.summary.toLowerCase().includes(kw)));
    this.setData({ shown });
  },

  onCatTap(e) {
    const cat = e.currentTarget.dataset.cat;
    if (!cat || cat === this.data.activeCat) return;
    this.setData({ activeCat: cat });
    this.filter();
  },

  onSearchInput(e) {
    this.setData({ kw: e.detail.value });
    this.filter();
  },

  onClearKw() {
    this.setData({ kw: '' });
    this.filter();
  },

  onArticleTap(e) {
    const id = e.currentTarget.dataset.id;
    if (!id) return;
    wx.navigateTo({ url: `/pages/article/article?id=${id}` });
  },

  onShareAppMessage() {
    return {
      title: '运营干货 · 创作者手册',
      path: '/pages/column/column'
    };
  }
});

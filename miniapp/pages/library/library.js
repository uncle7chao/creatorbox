/**
 * 素材库
 *
 * ⚠️ 关键设计决策：**不存播放地址**
 *   CDN 地址带签名会过期（实测 B站/快手地址有效期几十分钟到几小时），
 *   存了到时候也用不了 → 只存展示字段，重新解析一次即可拿新地址。
 *
 * 本期本地存储（wx.setStorageSync），上限 100 条。
 * 待接云端后改为服务端存储 + 跨设备同步。
 */

const { QUOTA } = require('../../utils/quota.js');
const themeUtil = require('../../utils/themes.js');

const KEY = 'cb_library';
const MAX_ITEMS = 100;

function readAll() {
  try {
    return wx.getStorageSync(KEY) || [];
  } catch (e) {
    return [];
  }
}

function writeAll(list) {
  try {
    wx.setStorageSync(KEY, list);
  } catch (e) {
    // 存储满：删掉最旧的 20 条再试一次
    wx.setStorageSync(KEY, list.slice(0, MAX_ITEMS - 20));
  }
}

Page({
  data: {
    theme: 'classic',
    items: [],
    allCount: 0,
    copyCount: 0,
    filter: 'all',          // all / material / copy
    todayCount: 0
  },

  onShow() {
    themeUtil.sync(this);
    this.refresh();
  },

  refresh() {
    const items = readAll();
    // 存储里的是裸对象，补上派生字段
    const decorated = items.map(it => ({
      ...it,
      timeText: this.formatTime(it.savedAt),
      platformLabel: it.platformLabel || it.platform || '未知'
    }));
    const copyCount = decorated.filter(it => it.item_type === 'copy').length;
    this.setData({
      items: this.applyFilter(decorated),
      allCount: decorated.length,
      copyCount,
      todayCount: QUOTA.cachedQuota().save_used || 0
    });
  },

  /** 文案库筛选（P0：素材与文案分开管理 —— 轻抖验证的需求） */
  applyFilter(list) {
    if (this.data.filter === 'copy') return list.filter(it => it.item_type === 'copy');
    if (this.data.filter === 'material') return list.filter(it => it.item_type !== 'copy');
    return list;
  },

  onFilter(e) {
    this.setData({ filter: e.currentTarget.dataset.f });
    this.refresh();
  },

  formatTime(ts) {
    if (!ts) return '';
    const d = new Date(ts);
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    if (sameDay) {
      return `今天 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    }
    return `${d.getMonth() + 1}月${d.getDate()}日`;
  },

  /** 保存到素材库（结果页保存成功后调用） */
  onAdd(e) {
    const r = e.detail;
    const item = {
      id: `${Date.now()}_${Math.floor(Math.random() * 1000)}`,
      title: r.title || '（无标题）',
      platform: r.platform,
      platformLabel: r.platformLabel,
      author: r.authorName || '',
      cover: r.cover || '',
      type: r.type,
      sourceText: r.inputText || '',
      savedAt: Date.now()
    };
    writeAll([item, ...readAll()].slice(0, MAX_ITEMS));
    this.refresh();
  },

  /** 点击历史项 → 重新解析（因为地址会过期，必须重新拿） */
  onReuse(e) {
    const { src } = e.currentTarget.dataset;
    if (!src) {
      wx.showToast({ title: '没有原始链接，无法重新解析', icon: 'none' });
      return;
    }
    const app = getApp();
    app.globalData.pendingInput = src;
    wx.switchTab({
      url: '/pages/index/index',
      success: () => {
        wx.showToast({ title: '已填入链接，点「开始解析」', icon: 'none' });
      }
    });
  },

  onPreview(e) {
    const { src } = e.currentTarget.dataset;
    if (src) wx.previewImage({ current: src, urls: [src] });
  },

  onDelete(e) {
    const { id } = e.currentTarget.dataset;
    wx.showModal({
      title: '删除这条记录',
      content: '只删除本地记录，不影响已保存到相册的文件',
      confirmText: '删除',
      confirmColor: '#C0392B',
      success: res => {
        if (!res.confirm) return;
        writeAll(readAll().filter(it => it.id !== id));
        this.refresh();
      }
    });
  },

  navHome() {
    wx.switchTab({ url: '/pages/index/index' });
  }
});
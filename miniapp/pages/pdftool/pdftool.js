/**
 * PDF 工具（P2 · 合并/提取页/加水印）
 *
 * 流程：wx.chooseMessageFile 从聊天选 PDF →
 *   · 合并：读 ArrayBuffer → multipart 手工构造 → /api/pdf/merge
 *   · 提取/水印：wx.uploadFile 直传 → 返回 /media/pdf/{name}
 * 结果：downloadFile → openDocument 预览（可转发/另存）。
 *
 * 约束：单文件 ≤10MB，合并 ≤5 个；产物服务端保留 1 天。
 */
const api = require('../../utils/api.js');
const { buildMultipart } = require('../../utils/multipart.js');
const themeUtil = require('../../utils/themes.js');

Page({
  data: {
    theme: 'classic',
    tab: 'merge',            // merge / extract / watermark
    files: [],               // 合并用：[{path, name, size}]
    single: null,            // 提取/水印用：{path, name, size}
    page: 1,                 // 提取页码
    watermarkText: '',
    busy: false,
    resultUrl: '',           // /media/pdf/xxx（相对）
    errMsg: ''
  },

  onShow() {
    themeUtil.sync(this);
  },

  switchTab(e) {
    if (this.data.busy) return;
    this.setData({ tab: e.currentTarget.dataset.t, errMsg: '', resultUrl: '' });
  },

  /** 选文件（合并：多选；单文件操作：单选） */
  choose(e) {
    const multi = this.data.tab === 'merge';
    const count = multi ? 5 : 1;
    wx.chooseMessageFile({
      count,
      type: 'file',
      extension: ['pdf'],
      success: res => {
        const picked = res.tempFiles.filter(f =>
          /\.pdf$/i.test(f.name) && f.size <= 10 * 1024 * 1024);
        const skipped = res.tempFiles.length - picked.length;
        if (multi) {
          const files = [...this.data.files, ...picked.map(f => ({
            path: f.path, name: f.name, size: this._fmt(f.size)
          }))].slice(0, 5);
          this.setData({ files, errMsg: '' });
        } else if (picked.length) {
          const f = picked[0];
          this.setData({ single: { path: f.path, name: f.name, size: this._fmt(f.size) }, errMsg: '' });
        }
        if (skipped > 0) {
          wx.showToast({ title: `${skipped} 个非PDF或超10MB已跳过`, icon: 'none' });
        }
      }
    });
  },

  removeFile(e) {
    const i = Number(e.currentTarget.dataset.i);
    const files = this.data.files.filter((_, x) => x !== i);
    this.setData({ files });
  },

  onPage(e) {
    this.setData({ page: Math.max(1, parseInt(e.detail.value, 10) || 1) });
  },

  onWmText(e) {
    this.setData({ watermarkText: e.detail.value || '' });
  },

  _fmt(n) {
    return n > 1024 * 1024 ? (n / 1048576).toFixed(1) + 'MB' :
           Math.max(1, Math.round(n / 1024)) + 'KB';
  },

  _fullUrl(u) {
    return u.startsWith('http') ? u : api.BASE_URL + u;
  },

  /** 主入口：按 tab 分发 */
  async run() {
    if (this.data.busy) return;
    const t = this.data.tab;
    if (t === 'merge' && this.data.files.length < 2) {
      this.setData({ errMsg: '合并至少需要 2 个 PDF' });
      return;
    }
    if (t !== 'merge' && !this.data.single) {
      this.setData({ errMsg: '请先选择 PDF 文件' });
      return;
    }
    if (t === 'watermark' && !this.data.watermarkText.trim()) {
      this.setData({ errMsg: '请输入水印文字' });
      return;
    }
    this.setData({ busy: true, errMsg: '', resultUrl: '' });
    wx.showLoading({ title: '处理中…', mask: true });
    try {
      let url = '';
      if (t === 'merge') url = await this._merge();
      else if (t === 'extract') url = await this._extract();
      else url = await this._watermark();
      this.setData({ resultUrl: url });
      // 自动打开预览
      wx.downloadFile({
        url: this._fullUrl(url),
        success: r => {
          wx.openDocument({ filePath: r.tempFilePath, fileType: 'pdf',
                            showMenu: true });
        }
      });
    } catch (e) {
      this.setData({ errMsg: e.message || '处理失败，请重试' });
    } finally {
      wx.hideLoading();
      this.setData({ busy: false });
    }
  },

  /** 合并：读 ArrayBuffer → 手工 multipart → wx.request */
  _merge() {
    return Promise.all(this.data.files.map(f => new Promise((res, rej) => {
      const fs = wx.getFileSystemManager();
      fs.readFile({ filePath: f.path, success: r => res({ filename: f.name, data: r.data }), fail: rej });
    }))).then(parts => new Promise((res, rej) => {
      const { body, contentType } = buildMultipart(
        parts.map(p => ({ name: 'files', filename: p.filename, data: p.data })));
      wx.request({
        url: api.BASE_URL + '/api/pdf/merge',
        method: 'POST',
        header: { 'content-type': contentType },
        data: body,
        responseType: 'text',
        success: r => {
          const j = typeof r.data === 'string' ? JSON.parse(r.data) : r.data;
          j.ok ? res(j.url) : rej(new Error(j.detail || '合并失败'));
        },
        fail: () => rej(new Error('连不上解析服务'))
      });
    }));
  },

  /** 单文件上传（提取/水印共用） */
  _upload(endpoint, formData) {
    return new Promise((res, rej) => {
      wx.uploadFile({
        url: api.BASE_URL + endpoint,
        filePath: this.data.single.path,
        name: 'file',
        formData,
        success: r => {
          try {
            const j = JSON.parse(r.data);
            j.ok ? res(j.url) : rej(new Error(j.detail || '处理失败'));
          } catch (pe) { rej(new Error('服务响应异常')); }
        },
        fail: () => rej(new Error('连不上解析服务'))
      });
    });
  },

  _extract() {
    return this._upload('/api/pdf/extract', { page: String(this.data.page) });
  },

  _watermark() {
    return this._upload('/api/pdf/watermark', { text: this.data.watermarkText.trim() });
  }
});

/**
 * 保存器：视频 / 图集 / 文案 的统一保存入口
 *
 * 从 result 页抽出（批量解析页也要用同一套逻辑）——
 * 此前保存在 result.js 里，批量页要么复制一份要么抽公共，抽公共。
 *
 * ⭐ 三条硬规则（历史踩坑沉淀）：
 *   1. wx.downloadFile 不返回 Promise → 必须手动包 resolve（P0 批量 bug 根因）
 *   2. XFile/分享只能接本地路径 —— 先下载后分享（v1 曾传远程 URL 必炸）
 *   3. AcFun 只有 m3u8 → mergeRequired 时直接拦，不发起下载
 */

const api = require('./api.js');
const { QUOTA } = require('./quota.js');

/** 下载一个文件（Promise 化） */
function download(url, ext) {
  return new Promise(resolve => {
    wx.downloadFile({
      url,
      filePath: `cb_${Date.now()}_${Math.floor(Math.random() * 1000)}.${ext}`,
      success: res => resolve({ ok: res.statusCode === 200, path: res.filePath || res.tempFilePath }),
      fail: () => resolve({ ok: false, path: '' })
    });
  });
}

/**
 * 批量保存文件到相册（图集/批量页共用）
 * @returns Promise<{done, failed, total}>
 */
function saveMany(urls, ext, onProgress) {
  const total = urls.length;
  let done = 0, failed = 0, finished = 0;

  const tasks = urls.map(url => new Promise(resolve => {
    wx.downloadFile({
      url,
      filePath: `cb_${Date.now()}_${Math.floor(Math.random() * 1000)}.${ext}`,
      success: res => {
        if (res.statusCode === 200) {
          wx.saveImageToPhotosAlbum({
            filePath: res.filePath || res.tempFilePath,
            success: () => { done++; },
            fail: () => { failed++; },
            complete: () => { finished++; resolve(); }
          });
        } else {
          failed++; finished++; resolve();
        }
      },
      fail: () => { failed++; finished++; resolve(); }
    });
  }));

  return Promise.all(tasks).then(() => ({ done, failed, total }));
}

/**
 * 保存视频（下载 → saveVideoToPhotosAlbum）
 * @returns Promise<{ok, saved, reason}>  reason: auth(权限)/download/merge
 */
function saveVideo(url) {
  return download(url, 'mp4').then(res => {
    if (!res.ok) return { ok: false, saved: false, reason: 'download' };
    return new Promise(resolve => {
      wx.saveVideoToPhotosAlbum({
        filePath: res.path,
        success: () => resolve({ ok: true, saved: true, path: res.path }),
        fail: err => {
          if (/auth|deny|permission/i.test(err.errMsg || '')) {
            resolve({ ok: false, saved: false, reason: 'auth', path: res.path });
          } else {
            resolve({ ok: false, saved: false, reason: 'save', path: res.path });
          }
        }
      });
    });
  });
}

/**
 * 保存单张图片到相册（封面 / 单张素材）
 * @returns Promise<{ok, reason}> reason: auth(权限被拒)/download(下载失败)
 *
 * ⭐ 为什么不直接用 saveMany([url])：
 *   saveMany 是批量语义，权限被拒时只记 failed++ 不给原因，
 *   用户只会看到「保存失败」，不知道是相册权限没开——而去开权限的动作
 *   完全无法引导。封面是本页面显式的第二产出，用户会反复点，
 *   必须给出「去设置里开权限」这种可操作的提示。
 */
function saveImage(url, ext) {
  return download(url, ext || 'jpg').then(res => {
    if (!res.ok) return { ok: false, reason: 'download' };
    return new Promise(resolve => {
      wx.saveImageToPhotosAlbum({
        filePath: res.path,
        success: () => resolve({ ok: true }),
        fail: err => {
          if (/auth|deny|permission/i.test(err.errMsg || '')) {
            resolve({ ok: false, reason: 'auth' });
          } else {
            resolve({ ok: false, reason: 'save' });
          }
        }
      });
    });
  });
}

/** 文案复制（提取文案双产出） */
function copyText(text) {
  return new Promise(resolve => {
    wx.setClipboardData({
      data: text,
      success: () => resolve(true),
      fail: () => resolve(false)
    });
  });
}

/**
 * 保存后的配额同步（保存成功才扣）
 * 服务端权威 —— 耗尽时返回 reason='quota_exhausted'
 */
function afterSaved(n = 1) {
  return QUOTA.consume(n);
}

module.exports = { download, saveMany, saveVideo, saveImage, copyText, afterSaved };
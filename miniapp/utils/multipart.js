/**
 * multipart/form-data 手工构造（PDF 合并等多文件上传用）
 *
 * 背景：wx.uploadFile 单请求只能传一个文件；合并 2-5 个 PDF 需要
 * 多文件同请求 —— 手工拼 multipart body，走 wx.request(ArrayBuffer)。
 *
 * 用法：
 *   const { body, contentType } = buildMultipart([
 *     { name: 'files', filename: 'a.pdf', data: arrayBuffer },
 *     { name: 'files', filename: 'b.pdf', data: arrayBuffer }
 *   ]);
 *   wx.request({ url, method: 'POST', header: { 'content-type': contentType },
 *                data: body, responseType: 'arraybuffer' })
 */

/** ArrayBuffer ← string（UTF-8） */
function _enc(s) {
  const u = new Uint8Array(s.length * 3);
  let n = 0;
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c < 0x80) u[n++] = c;
    else if (c < 0x800) {
      u[n++] = 0xC0 | (c >> 6); u[n++] = 0x80 | (c & 63);
    } else {
      u[n++] = 0xE0 | (c >> 12);
      u[n++] = 0x80 | ((c >> 6) & 63);
      u[n++] = 0x80 | (c & 63);
    }
  }
  return u.slice(0, n).buffer;
}

function _cat(parts) {
  let total = 0;
  parts.forEach(p => { total += p.byteLength; });
  const out = new Uint8Array(total);
  let off = 0;
  parts.forEach(p => {
    out.set(new Uint8Array(p), off);
    off += p.byteLength;
  });
  return out.buffer;
}

/**
 * fields: [{ name, filename, data(ArrayBuffer), mime? }]
 * 返回 { body: ArrayBuffer, contentType: string }
 */
function buildMultipart(fields) {
  const boundary = 'cbpdf' + Date.now().toString(36) +
                   Math.random().toString(36).slice(2, 8);
  const parts = [];
  fields.forEach(f => {
    parts.push(_enc(
      `--${boundary}\r\nContent-Disposition: form-data; name="${f.name}"; ` +
      `filename="${(f.filename || 'file.pdf').replace(/"/g, '')}"\r\n` +
      `Content-Type: ${f.mime || 'application/pdf'}\r\n\r\n`));
    parts.push(f.data);
    parts.push(_enc('\r\n'));
  });
  parts.push(_enc(`--${boundary}--\r\n`));
  return {
    body: _cat(parts),
    contentType: `multipart/form-data; boundary=${boundary}`
  };
}

module.exports = { buildMultipart };

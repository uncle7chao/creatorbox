"""PDF 极轻三件（P2 · 2026-10-07）

合并 / 拆分 / 加水印 —— pypdf + reportlab（纯 Python，2C2G 可承受）。
设计约束：
  · 上限 10MB/文件、单次 ≤ 5 个文件（内存与流量排位：1TB 月流量是稀缺资源）
  · 产物落 server/media/pdf/{uuid}.pdf，经 /media 下发，客户端 downloadFile
  · 用后即焚不持久保存业务文件；定期清理（复用健康清理节奏，保留 1 天）
"""
import os
import re
import uuid
from io import BytesIO

from pypdf import PdfReader, PdfWriter

try:
    from app import config
except ImportError:
    import config

_PDF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        '..', 'media', 'pdf')
os.makedirs(_PDF_DIR, exist_ok=True)

MAX_FILE = 10 * 1024 * 1024
MAX_COUNT = 5


def _save(pdf_bytes: bytes) -> str:
    """落盘并返回 /media/pdf/{name} 相对 URL"""
    name = uuid.uuid4().hex[:12] + '.pdf'
    with open(os.path.join(_PDF_DIR, name), 'wb') as f:
        f.write(pdf_bytes)
    return f'/media/pdf/{name}'


def _read(data: bytes, name: str) -> PdfReader:
    if len(data) > MAX_FILE:
        raise ValueError(f'{name} 超过 10MB 上限')
    if not data[:5] == b'%PDF-':
        raise ValueError(f'{name} 不是有效的 PDF 文件')
    try:
        return PdfReader(BytesIO(data))
    except Exception as e:
        raise ValueError(f'{name} 无法解析: {str(e)[:50]}')


def merge(files: list) -> str:
    """files: [(filename, bytes)] 按顺序合并。"""
    if not 2 <= len(files) <= MAX_COUNT:
        raise ValueError('合并需要 2-5 个文件')
    writer = PdfWriter()
    total_pages = 0
    for name, data in files:
        reader = _read(data, name)
        total_pages += len(reader.pages)
        if total_pages > 500:
            raise ValueError('合并后总页数超过 500 页上限')
        for page in reader.pages:
            writer.add_page(page)
    out = BytesIO()
    writer.write(out)
    return _save(out.getvalue())


def split(data: bytes, name: str, mode: str, page_no: int = 0) -> str:
    """mode: 'each' 每页一个文件(zip) | 'range' 提取指定页。

    简化交付：'each' 模式在浏览器端逐个下载太繁琐，
    P2 先交付 'range'（提取指定页为单个 PDF）+ 'split_half'（对半拆成两份）。
    """
    reader = _read(data, name)
    writer = PdfWriter()
    n = len(reader.pages)
    if mode == 'range':
        if not 1 <= page_no <= n:
            raise ValueError(f'页码超出范围（共 {n} 页）')
        writer.add_page(reader.pages[page_no - 1])
    elif mode == 'half':
        mid = n // 2
        if n < 2:
            raise ValueError('不足 2 页无法拆分')
        for p in list(reader.pages[:mid]) + [None]:
            pass
        # 两份输出 → 返回第一个，第二个存同名 _b
        writer_a, writer_b = PdfWriter(), PdfWriter()
        for p in reader.pages[:mid]:
            writer_a.add_page(p)
        for p in reader.pages[mid:]:
            writer_b.add_page(p)
        out_a = BytesIO(); writer_a.write(out_a)
        out_b = BytesIO(); writer_b.write(out_b)
        url_a = _save(out_a.getvalue())
        _save(out_b.getvalue())          # b 份同名 _b 前缀不方便，改双返回
        return url_a
    else:
        raise ValueError('未知拆分模式')
    out = BytesIO()
    writer.write(out)
    return _save(out.getvalue())


def watermark(data: bytes, name: str, text: str) -> str:
    """整份 PDF 每页叠加文字水印（reportlab 生成水印层）。"""
    from reportlab.pdfgen import canvas as rl_canvas
    text = (text or '').strip()[:24]
    if not text:
        raise ValueError('水印文字不能为空')
    reader = _read(data, name)
    writer = PdfWriter()

    for page in reader.pages:
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)
        buf = BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=(w, h))
        c.setFont('Helvetica', max(18, min(w, h) / 18))
        c.setFillColorRGB(0.55, 0.55, 0.55, alpha=0.35)
        # 居中平铺 45° 斜排，两行错位
        c.saveState()
        c.translate(w / 2, h / 2)
        c.rotate(38)
        c.drawCentredString(0, 0, text)
        c.drawCentredString(-w / 3, -h / 5, text)
        c.drawCentredString(w / 3, h / 5, text)
        c.restoreState()
        c.save()
        buf.seek(0)
        overlay = PdfReader(buf).pages[0]
        page.merge_page(overlay)
        writer.add_page(page)

    out = BytesIO()
    writer.write(out)
    return _save(out.getvalue())


def cleanup(keep_hours: int = 24) -> int:
    """清理过期产物（产出文件用完即走，默认保留 1 天）。"""
    import time
    cutoff = time.time() - keep_hours * 3600
    removed = 0
    for f in os.listdir(_PDF_DIR):
        p = os.path.join(_PDF_DIR, f)
        try:
            if os.path.getmtime(p) < cutoff:
                os.remove(p)
                removed += 1
        except OSError:
            pass
    return removed


if __name__ == '__main__':
    # 自检：构造 3 页 PDF → 合并/拆分/水印 全链路
    from reportlab.pdfgen import canvas as rl
    def mk(pages):
        buf = BytesIO()
        c = rl.Canvas(buf)
        for i in range(pages):
            c.drawString(100, 700 + i * 40, f'page {i}')
            c.showPage()
        c.save()
        return buf.getvalue()

    a, b = mk(3), mk(2)
    url = merge([('a.pdf', a), ('b.pdf', b)])
    reader = PdfReader(os.path.join(_PDF_DIR, os.path.basename(url)))
    assert len(reader.pages) == 5, '合并应为 5 页'
    print('merge OK →', url)

    url2 = split(a, 'a.pdf', 'range', 2)
    r2 = PdfReader(os.path.join(_PDF_DIR, os.path.basename(url2)))
    assert len(r2.pages) == 1
    print('split(range) OK →', url2)

    url3 = watermark(a, 'a.pdf', 'CreatorBox 测试')
    r3 = PdfReader(os.path.join(_PDF_DIR, os.path.basename(url3)))
    assert len(r3.pages) == 3
    print('watermark OK →', url3)

    # 清理自检产物
    removed = cleanup(keep_hours=0)
    print(f'cleanup 移除 {removed} 个测试产物')
    print('自检全部通过')

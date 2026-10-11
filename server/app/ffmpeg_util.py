"""ffmpeg 可执行文件定位 —— 支持三种来源，优先级从高到低

设计目标：**生产环境零外部依赖**。
`imageio-ffmpeg` 这个 pip 包自带静态编译的 ffmpeg 二进制，
装上就能用，不需要运维手动装 ffmpeg。

⚠️ 许可提醒：imageio-ffmpeg 附带的二进制是 **GPL 构建**
   （实测 `configuration:` 里带 --enable-gpl）。
   - **作为独立进程调用**（subprocess）：通常不构成衍生作品，
     与自己代码是「mere aggregation」，商用风险低
   - **静态链接进你的二进制 / 打进单文件可执行**：会触发 GPL 传染
   - **打进 Docker 镜像分发**：需注意 GPL 的分发条款
   → 闭源商用建议：(1) 只 subprocess 调用 (2) 镜像里放系统包
     ffmpeg 而非这个 wheel (3) 上线前让法务确认
"""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import List, Optional

# 常见系统安装位置（Linux/Docker 与 Windows）
_SYSTEM_PATHS = [
    '/usr/bin/ffmpeg', '/usr/local/bin/ffmpeg', '/opt/homebrew/bin/ffmpeg',
    '/snap/bin/ffmpeg',
    r'C:\ffmpeg\bin\ffmpeg.exe',
    r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
    r'C:\ProgramData\chocolatey\bin\ffmpeg.exe',
]

_env_exe: Optional[str] = None
_env_checked = False


def _from_imageio() -> Optional[str]:
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        return exe if exe and os.path.exists(exe) else None
    except Exception:
        return None


def get_ffmpeg() -> Optional[str]:
    """定位可用的 ffmpeg。找不到返回 None（调用方必须优雅降级）"""
    global _env_exe, _env_checked

    # 1. 显式环境变量（部署时最可控）
    exe = os.getenv('CB_FFMPEG_PATH', '').strip()
    if exe and os.path.exists(exe):
        return exe

    if _env_checked:
        return _env_exe
    _env_checked = True

    # 2. 系统 PATH
    exe = shutil.which('ffmpeg')
    if exe:
        _env_exe = exe
        return exe

    # 3. 常见安装位置
    for p in _SYSTEM_PATHS:
        if os.path.exists(p):
            _env_exe = p
            return p

    # 4. pip 包自带的静态二进制（生产推荐）
    _env_exe = _from_imageio()
    return _env_exe


def is_available() -> bool:
    """真实跑一次 -version 确认可执行（不只判断文件存在）"""
    exe = get_ffmpeg()
    if not exe:
        return False
    try:
        r = subprocess.run([exe, '-version'], capture_output=True,
                           timeout=15)
        return r.returncode == 0 and b'ffmpeg version' in r.stdout
    except Exception:
        return False


def version() -> str:
    exe = get_ffmpeg()
    if not exe:
        return ''
    try:
        r = subprocess.run([exe, '-version'], capture_output=True,
                           timeout=15)
        first = r.stdout.decode('utf-8', 'ignore').splitlines()
        return first[0] if first else ''
    except Exception:
        return ''


def capabilities() -> dict:
    """探测本机 ffmpeg 支持的关键能力（合并前先确认，别等失败才发现）"""
    exe = get_ffmpeg()
    out = {
        'available': False, 'path': exe or '', 'version': '',
        'libx264': False, 'aac': False, 'mp4_muxer': False,
        'faststart': False, 'tls': False,
    }
    if not exe:
        return out
    try:
        r = subprocess.run([exe, '-hide_banner', '-codecs'],
                           capture_output=True, timeout=20)
        text = r.stdout.decode('utf-8', 'ignore')
        out['libx264'] = 'libx264' in text
        out['aac'] = ' aac ' in text
        r2 = subprocess.run(
            [exe, '-hide_banner', '-protocols'],
            capture_output=True, timeout=20)
        out['tls'] = 'https' in r2.stdout.decode('utf-8', 'ignore').lower()
        r3 = subprocess.run(
            [exe, '-hide_banner', '-h', 'muxer=mp4'],
            capture_output=True, timeout=20)
        out['mp4_muxer'] = r3.returncode == 0
        out['faststart'] = 'faststart' in \
            r3.stdout.decode('utf-8', 'ignore')
        out['version'] = version()
        out['available'] = out['mp4_muxer']
    except Exception:
        pass
    return out


def build_cmd(src: str, dst: str, *, reencode: bool = False,
              extra_headers: Optional[List[str]] = None) -> List[str]:
    """拼ffmpeg 命令行

    默认**不重编码**（-c copy）：纯拼接，速度快、无画质损失、秒级完成。
    只有源是 HEVC(265) 而目标设备不兼容时才需要 reencode=True。

    `-movflags +faststart` 把 moov 原子挪到文件头，
    否则小程序/移动端无法边下边播（必须等整个文件下完）。
    """
    exe = get_ffmpeg() or 'ffmpeg'
    cmd = [exe, '-hide_banner', '-loglevel', 'error', '-y']
    # 输入侧：某些平台 CDN 需要 Referer/UA
    for h in (extra_headers or []):
        cmd += ['-headers', h]
    cmd += ['-i', src]
    if reencode:
        cmd += ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22',
                '-c:a', 'aac', '-b:a', '128k']
    else:
        cmd += ['-c', 'copy']
    cmd += ['-movflags', '+faststart', dst]
    return cmd


if __name__ == '__main__':
    import json
    print(json.dumps(capabilities(), ensure_ascii=False, indent=2))

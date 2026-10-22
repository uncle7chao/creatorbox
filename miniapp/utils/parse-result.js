/**
 * 解析结果数据模型
 *
 * ⭐ 与 app/models/parse_result.dart 结构对齐 —— 两个客户端读同一份契约，
 *    字段名保持一致，改服务端时只改一处认知。
 *
 * 设计原则（沿用服务端元信息规范层 meta.py 的教训）：
 *   · 可选键始终存在（空值也给 '' 或 {}），前端不判断「键是否存在」
 *   · 数字与展示文本分两个字段（stats / stats_text）
 *   · 接口没给就留空，不推算、不编造
 */

const { PLATFORM_LABELS } = require('./api.js');

class ParseResult {
  constructor(raw) {
    const r = raw || {};
    const m = r.meta || {};

    // ---- 状态 ----
    this.success = !!r.success;
    this.error = r.error || '';

    // ---- 基础 ----
    this.platform = r.platform || '';
    this.platformLabel = PLATFORM_LABELS[r.platform] || r.platform || '未知';
    // type: 'video' | 'image'
    this.type = r.type || '';
    this.method = r.method || '';

    // ---- 标题（含来源，可信度不同）----
    this.title = m.title || '';
    // ssr / share_text / desc_head / template_skipped
    this.titleSource = m.title_source || '';
    this.description = m.description || '';

    // ---- 覆盖情况（已知缺口如实展示，不编造）----
    const cov = {
      cover: !!m.cover,
      authorName: !!m.author_name,
      authorAvatar: !!m.author_avatar,
      duration: typeof m.duration_s === 'number' && m.duration_s > 0,
      publishTime: !!m.publish_time,
      stats: !!(m.stats && Object.keys(m.stats).length),
      tags: !!(m.tags && m.tags.length)
    };
    this.coverage = cov;

    // ---- 作者 ----
    this.authorName = m.author_name || '';
    this.authorId = m.author_id || '';
    this.authorAvatar = m.author_avatar || '';
    this.cover = m.cover || '';

    // ---- BGM（2026-10-11，抖音先行；其他平台字段缺省为空 = 不显示）----
    this.musicUrl = m.music_url || '';
    this.musicTitle = m.music_title || '';
    this.musicAuthor = m.music_author || '';

    // ---- 字幕文案（2026-10-11，ytdlp 引擎下发：YouTube/FB；顶层字段非 meta）----
    this.subtitleText = (r.subtitle_text || m.subtitle_text || '');
    this.subtitleLang = (r.subtitle_lang || m.subtitle_lang || '');
    this.subtitleAuto = !!(r.subtitle_auto || m.subtitle_auto);

    // ---- 时长 / 时间 ----
    this.durationS = typeof m.duration_s === 'number' ? m.duration_s : null;
    // ⭐ 文件大小（2026-10-22，竞品对齐：视频卡显示「时长+大小」）
    // 大小文本由服务端格式化（size_text）—— 口径统一放一处，
    // 免得各端各算一套出现「31.9MB」vs「33,449,661 字节」这种不一致。
    // ⚠️ duration_text 服务端也下发，但本文件已有 durationText getter
    //    （本地算，格式「3 分 33 秒」），保持用本地那个，别重复定义。
    this.fileSize = r.size || 0;
    this.fileSizeText = r.size_text || '';
    this.publishTime = m.publish_time || '';
    this.publishTimeText = m.publish_time_text || '';

    // ---- 互动数据 ----
    // stats：数字（用于排序统计）· stats_text：原文（用于展示）
    this.stats = m.stats || {};
    this.statsText = m.stats_text || {};
    this.tags = m.tags || [];
    this.extra = m.extra || {};

    // ---- 视频 ----
    this.videoUrl = r.video_url || '';
    this.quality = r.quality || '';
    this.options = Array.isArray(r.options) ? r.options : [];
    this.optionsCount = this.options.length;
    this.noWatermark = r.no_watermark !== false;
    this.needProxy = !!r.need_proxy;
    // 匿名可用上限（超出的清晰度要上锁）
    this.anonymousMaxHeight = r.anonymous_max_height || 720;

    // ---- 图集 ----
    this.images = Array.isArray(r.images) ? r.images : [];
    this.imageCount = this.images.length;

    // ---- 能力标记 ----
    this.truncated = !!r.truncated;          // 搜狐 >30s 只有试看片段
    this.mergeRequired = !!r.merge_required; // AcFun 只有 m3u8，需服务端合并

    // ---- 分享原文（结果页「原链接」用）----
    this.inputText = r.input_text || '';
  }

  get isVideo() {
    return this.type === 'video';
  }

  get isImage() {
    return this.type === 'image';
  }

  /**
   * 推荐清晰度：优先未超匿名上限的最高档
   *
   * ⚠️ 不能简单取 options[0] —— 服务端返回顺序不保证按高度排。
   */
  get recommendedOption() {
    if (!this.isVideo || !this.options.length) return null;
    const free = this.options.filter(o => (o.height || 0) <= this.anonymousMaxHeight);
    const pool = free.length ? free : this.options;
    return pool.reduce((best, o) => ((o.height || 0) > (best.height || 0) ? o : best));
  }

  /** 某一档是否需要付费/看广告解锁 */
  isLocked(option) {
    return (option.height || 0) > this.anonymousMaxHeight;
  }

  /** 时长文案，如「3 分 33 秒」 */
  get durationText() {
    if (this.durationS === null) return '';
    const s = Math.round(this.durationS);
    const m = Math.floor(s / 60);
    const rest = s % 60;
    if (m > 0) return `${m} 分 ${rest} 秒`;
    return `${rest} 秒`;
  }

  /**
   * 互动数据展示行
   *
   * ⚠️ 只展示有值的 —— AcFun / 搜狐 接口不下发互动数据，
   *    显示「0」会被误认为「真的没人看」。
   */
  get statsLine() {
    const out = [];
    const pairs = [
      ['view', '播放'],
      ['like', '点赞'],
      ['comment', '评论'],
      ['collect', '收藏']
    ];
    pairs.forEach(([key, label]) => {
      const text = this.statsText[key];
      const num = this.stats[key];
      if (text) out.push({ label, text: String(text) });
      else if (typeof num === 'number' && num > 0) {
        out.push({ label, text: formatCount(num) });
      }
    });
    return out;
  }

  /**
   * 标题可信度提示
   *
   * 诚实性设计：标题靠推断时要告诉用户，不能让他以为那就是原文标题。
   */
  get titleHint() {
    if (!this.title) return '该平台未提供标题';
    if (this.titleSource === 'share_text') return '';
    if (this.titleSource === 'desc_head') return '标题由文案推断，可能不完整';
    if (this.titleSource === 'template_skipped') return '平台未提供标题，已用文案首句';
    return '';
  }

  /** 需要提示用户的情况（结果页顶部琥珀条） */
  get notices() {
    const out = [];
    if (this.truncated) {
      out.push('长视频仅提供前 30 秒试看片段，完整版需在平台观看');
    }
    if (this.mergeRequired) {
      out.push('该平台需服务端合并下载，稍候片刻');
    }
    if (this.needProxy) {
      out.push('该平台下载需服务器中转，会稍慢一些');
    }
    return out;
  }
}

/** 数字转中文展示：12345 → 1.2万 */
function formatCount(n) {
  if (typeof n !== 'number') return String(n);
  if (n >= 100000000) return (n / 100000000).toFixed(1).replace(/\.0$/, '') + '亿';
  if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, '') + '万';
  return String(n);
}

/**
 * 构造失败结果
 *
 * 服务端返回 success:false 时，也要给出结构完整的对象，
 * 免得页面里到处判空。
 */
function makeFailure(errMsg) {
  const r = new ParseResult({ success: false, error: errMsg });
  return r;
}

module.exports = { ParseResult, formatCount, makeFailure };
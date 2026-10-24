/**
 * 页面渲染用的 mock 数据（2026-10-24）
 *
 * 为什么需要：转换器不执行业务逻辑，页面 onLoad 里的请求不会跑，
 *            所以 data 全是初始空值，渲染出来是空壳。
 *            这里给每个页面一份「加载完成后」的合理数据。
 *
 * ⚠️ 字段必须和页面 js 的 data / setData 一致，否则渲染出空白。
 *    改页面结构时，这份 mock 也要跟着改（否则预览会失真）。
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');

/** 读本地图转 data URI（避免路径问题，保证预览自包含） */
function img(rel) {
  try {
    const p = path.join(ROOT, rel);
    if (!fs.existsSync(p)) return '';
    const ext = path.extname(p).slice(1).toLowerCase();
    const mime = ext === 'png' ? 'image/png' : (ext === 'webp' ? 'image/webp' : 'image/jpeg');
    return `data:${mime};base64,` + fs.readFileSync(p).toString('base64');
  } catch (e) { return ''; }
}

const COVER = img('test/out/cover_small.webp') || img('miniapp/images/home/batch-classic.png');

const PARSE_TITLE = '外卖42元一份的猪脚饭真的好吃吗？#分享你的快餐推荐 #猪脚饭';
const COPY_TEXT = '外卖42元一份的猪脚饭真的好吃吗？ #分享你的快餐推荐 #猪脚饭 #真实生活分享计划 #美食分享';

/** 结果页四行素材（结构对齐 pages/result/result.js 的 buildAssets） */
function assetRows() {
  return [
    { key: 'video', kind: 'video', label: '视频', empty: false, preview: '',
      acts: [{ key: 'saveVideo', label: '保存到相册', main: true }] },
    { key: 'cover', kind: 'cover', label: '封面', empty: false, preview: '',
      acts: [{ key: 'saveCover', label: '保存封面', main: true }] },
    { key: 'text', kind: 'text', label: '标题文案', empty: false,
      preview: '外卖42元一份的猪脚饭真的好吃吗？',
      acts: [{ key: 'copyTitle', label: '复制标题' }, { key: 'copyCopy', label: '复制文案', main: true }] },
    { key: 'tags', kind: 'tags', label: '话题', empty: false,
      preview: '#分享你的快餐推荐 #猪脚饭 #美食分享',
      acts: [{ key: 'copyTags', label: '复制话题', main: true }] },
    { key: 'subtitle', kind: 'text', label: '字幕', empty: true, emptyText: '本视频没有字幕',
      preview: '', acts: [{ key: 'copySubtitle', label: '复制字幕' }] },
    { key: 'audio', kind: 'audio', label: '背景音乐', empty: false,
      preview: '原声 - 小张的日常',
      acts: [{ key: 'toggleBgm', label: '试听', main: true }, { key: 'copyBgm', label: '复制链接' }] },
  ];
}

module.exports = {
  _default: { theme: 'classic' },

  // ── 首页 ─────────────────────────────────────────────
  index: {
    theme: 'classic',
    input: '',
    parsing: false,
    errorMsg: '',
    progress: 0,
    stepText: '',
    showPopup: false,
    heroImages: [],
    heroLink: '',
    savedToday: 1,
    saveQuota: 3,
    serviceOk: true,
    serviceMsg: '已连接',
    platformCount: 13,
    platforms: ['抖音', 'B站', '好看视频', '百度视频', '微博', 'AcFun', '小红书', '快手', '搜狐'],
    platformTags: [
      { key: 'douyin', name: '抖音' }, { key: 'bilibili', name: 'B站' },
      { key: 'haokan', name: '好看视频' }, { key: 'baidu', name: '百度视频' },
      { key: 'weibo', name: '微博' }, { key: 'acfun', name: 'AcFun' },
      { key: 'xhs', name: '小红书' }, { key: 'kuaishou', name: '快手' },
      { key: 'sohu', name: '搜狐' },
    ],
    freeMaxHeight: 720,
    banners: [
      { title: '批量解析', desc: '一次 10 条', tag: 'NEW' },
      { title: '违禁词检测', desc: '发布前先过一遍', tag: '' },
    ],
  },

  // ── 结果页 ───────────────────────────────────────────
  result: {
    theme: 'classic',
    loading: false,
    r: null,
    title: PARSE_TITLE,
    authorLine: '小张的日常 · 00:42',
    cover: COVER,
    coverRaw: COVER,
    bgmShow: true,
    bgmLine: '原声 - 小张的日常',
    bgmUrl: 'https://example.com/bgm.mp3',
    bgmPlaying: false,
    isVideo: true,
    isImage: false,
    notices: [],
    titleHint: '',
    statsLine: ['8分14秒', '73.1 MB', '1080P'],
    tags: ['分享你的快餐推荐', '猪脚饭', '真实生活分享计划', '美食分享', '快餐'],
    images: [],
    copyText: COPY_TEXT,
    copyTags: ['分享你的快餐推荐', '猪脚饭', '真实生活分享计划'],
    options: [
      { label: '1080P 原画', height: 1080, locked: false },
      { label: '720P 高清', height: 720, locked: false },
      { label: '540P 流畅', height: 540, locked: false },
    ],
    selectedIdx: 1,
    freeMaxHeight: 720,
    saving: false,
    assets: assetRows(),
    durationText: '8分14秒',
    fileSizeText: '73.1 MB',
    quotaLeft: 1,
    quotaTotal: 3,
    subtitleText: '',
    subtitleAuto: false,
    subtitleLen: 0,
    subtitleLang: '',
    subtitlePreview: '',
    errMsg: '',
  },

  // ── 批量解析 ─────────────────────────────────────────
  batch: {
    theme: 'classic',
    input: '',
    parsing: false,
    batchLimit: 10,
    bTotal: 3,
    bProgress: 3,
    okCount: 3,
    failCount: 0,
    errMsg: '',
    results: [
      { url: 'https://v.douyin.com/ntaaK4aH9pE/', ok: true, title: '外卖42元一份的猪脚饭真的好吃吗？', platform: '抖音', cover: COVER },
      { url: 'https://www.bilibili.com/video/BV1GJ411x7h7', ok: true, title: '【官方 MV】Never Gonna Give You Up', platform: 'B站', cover: '' },
      { url: 'https://mr.baidu.com/r/24UZVL6dTCo', ok: false, title: '', platform: '', err: '视频已下架' },
    ],
  },

  // ── 工具箱 ───────────────────────────────────────────
  toolbox: {
    theme: 'classic',
    platformCount: 13,
    // ⚠️ 字段名是 item.type（不是 key/cls）：模板里按 type 决定图标图形与底色
    //    （icon 是纯 CSS 画的：g-dl / g-layers / g-doc / g-pod / g-shield）
    live: [
      { type: 'parse', name: '链接解析', desc: '13 个平台' },
      { type: 'batch', name: '批量解析', desc: '一次 10 条' },
      { type: 'rank', name: '热榜', desc: '实时热点' },
      { type: 'copy', name: '文案提取', desc: '标题 / 正文' },
      { type: 'banned', name: '违禁词检测', desc: '发布前自查' },
    ],
    placeholders: [
      { name: '音频提文案', desc: '视频转文字' },
      { name: '图片提文案', desc: 'OCR 识别' },
      { name: 'AI 创作助手', desc: 'PC / App 可用', pcOnly: true },
      { name: '账号工具', desc: '数据分析' },
      { name: '文件转换', desc: '办公文档' },
      { name: '智能修复', desc: '敬请期待' },
    ],
  },

  // ── 素材库 ───────────────────────────────────────────
  library: {
    theme: 'classic',
    allCount: 12,
    todayCount: 3,
    copyCount: 2,
    filter: 'all',
    all: true,
    // ⚠️ 字段：platformLabel / timeText / author / sourceText（不是 platform/dateText）
    items: [
      { id: '1', title: '外卖42元一份的猪脚饭真的好吃吗？', platformLabel: '抖音',
        author: '小张的日常', timeText: '今天 14:20', cover: COVER,
        sourceText: 'https://v.douyin.com/ntaaK4aH9pE/' },
      { id: '2', title: '【官方 MV】Never Gonna Give You Up', platformLabel: 'B站',
        author: 'Rick Astley', timeText: '今天 11:05', cover: COVER,
        sourceText: 'https://www.bilibili.com/video/BV1GJ411x7h7' },
      { id: '3', title: '林萧，你真成主编了', platformLabel: '小红书',
        author: '', timeText: '昨天 20:31', cover: '',
        sourceText: 'https://www.xiaohongshu.com/discovery/item/6a827209' },
      { id: '4', title: '8分14秒的百度视频是怎么火的', platformLabel: '百度视频',
        author: '', timeText: '昨天 09:12', cover: '',
        sourceText: 'https://mr.baidu.com/r/24UZVL6dTCo' },
    ],
  },

  // ── 热榜 ─────────────────────────────────────────────
  ranking: {
    theme: 'classic',
    loading: false,
    errorMsg: '',
    activeKey: 'bilibili',
    activeLabel: 'B站',
    updatedText: '更新于 22:10',
    soon: false,
    platforms: [
      { key: 'bilibili', label: 'B站' },
      { key: 'douyin', label: '抖音' },
      { key: 'weibo', label: '微博' },
      { key: 'baidu', label: '百度' },
      { key: 'xhs', label: '小红书' },
    ],
    // ⚠️ 字段：rank / title / hot / medal(金1银2铜3) / heatPct / author / live / kind
    items: [
      { rank: 1, title: '国产大模型又开源了', hot: '982.1万', medal: 'gold',
        heatPct: 100, author: '科技观察', live: true, kind: 'video' },
      { rank: 2, title: '外卖42元一份的猪脚饭', hot: '761.4万', medal: 'silver',
        heatPct: 77, author: '小张的日常', live: false, kind: 'video' },
      { rank: 3, title: '为什么年轻人不爱换手机了', hot: '643.0万', medal: 'bronze',
        heatPct: 65, author: '数码闲聊', live: false, kind: 'video' },
      { rank: 4, title: '秋天的第一杯奶茶', hot: '521.8万', medal: '',
        heatPct: 53, author: '美食日记', live: false, kind: 'video' },
      { rank: 5, title: '凌晨四点的菜市场', hot: '487.2万', medal: '',
        heatPct: 49, author: '城市切片', live: false, kind: 'video' },
    ],
  },

  // ── 会员中心 ─────────────────────────────────────────
  member: {
    theme: 'classic',
    isMember: false,
    price: '9.9',
    skin: 'classic',
    hd: true,
    cloud: true,
    batch: true,
    save: true,
    // ⚠️ 字段是 name / desc / cls（cls 决定图标图形：batch/hd/save/cloud/fast）
    perks: [
      { name: '批量解析', desc: '单次 10 条', cls: 'batch' },
      { name: '高清画质', desc: '最高 1080P', cls: 'hd' },
      { name: '保存不限次', desc: '每日上限解除', cls: 'save' },
      { name: '云端素材库', desc: '多设备同步', cls: 'cloud' },
      { name: '新功能优先', desc: '抢先体验', cls: 'fast' },
    ],
    themeList: [
      { key: 'classic', name: '经典橙金' },
      { key: 'dark', name: '午夜暗黑' },
      { key: 'jade', name: '青玉' },
      { key: 'sakura', name: '樱粉' },
    ],
  },

  // ── 积分 ─────────────────────────────────────────────
  points: {
    theme: 'classic',
    balance: 240,
    signedToday: false,
    streak: 3,
    today: 10,
    redeemCost: 100,
    redeemableDays: 2,
    member: false,
    message: '连续签到 7 天可额外 +20 积分',
    done: false,
    errMsg: '',
    wk: [
      { day: '一', done: true }, { day: '二', done: true }, { day: '三', done: true },
      { day: '四', done: false }, { day: '五', done: false }, { day: '六', done: false },
      { day: '日', done: false },
    ],
  },

  // ── 违禁词检测 ───────────────────────────────────────
  banned: {
    theme: 'classic',
    text: '这款产品全网最低价，绝对有效，三天见效，加微信领取',
    checking: false,
    checked: true,
    clean: false,
    hit: 4,
    total: 26,
    used: 4,
    limit: 20,
    riskLevel: 'high',
    isMember: false,
    disabled: false,
    segments: [
      { t: '这款产品', hit: false },
      { t: '全网最低价', hit: true, group: 'adlaw' },
      { t: '，绝对有效', hit: true, group: 'medical' },
      { t: '，三天见效', hit: true, group: 'medical' },
      { t: '，加微信领取', hit: true, group: 'induce' },
    ],
    // ⚠️ words 是对象数组：{word, count, suggest}（模板读 w.word / w.count / w.suggest）
    //    risk 是直接输出的文案，不是枚举值
    groups: [
      { name: '广告法', count: 3, risk: '高风险 · 罚款重灾区', words: [
        { word: '全网最低价', count: 2, suggest: '优惠价' },
        { word: '国家级', count: 1, suggest: '（删除）' }] },
      { name: '医疗夸大', count: 3, risk: '高风险 · 需资质', words: [
        { word: '绝对有效', count: 2, suggest: '可能有帮助' },
        { word: '三天见效', count: 1, suggest: '（删除）' }] },
      { name: '诱导引流', count: 1, risk: '中风险 · 易限流', words: [
        { word: '加微信', count: 1, suggest: '主页联系' }] },
    ],
  },

  // ── PDF 工具 ─────────────────────────────────────────
  pdftool: {
    theme: 'classic',
    tab: 'merge',
    busy: false,
    errMsg: '',
    resultUrl: '',
    page: '1',
    watermarkText: '内部资料',
    files: [
      { name: '合同-2026.pdf', size: '1.2 MB' },
      { name: '附件A.pdf', size: '840 KB' },
    ],
    merge: true, single: false, extract: false, watermark: false,
  },

  // ── 提词器 ───────────────────────────────────────────
  teleprompter: {
    theme: 'classic',
    playing: false,
    paused: true,
    speed: 3,
    fontSize: 28,
    scrollTop: 0,
    errMsg: '',
    script: '大家好，今天给大家分享一个猪脚饭的探店。\n\n这家店在巷子里，一份 42 元，分量给得很足。\n\n先看这个猪脚，皮是焦的那种，咬下去有胶质感。\n\n米饭用的是香米，粒粒分明。\n\n最后说结论：这个价位，值。',
  },

  // ── 栏目页 ───────────────────────────────────────────
  column: {
    theme: 'classic',
    active: 'all',
    activeCat: 'all',
    kw: '',
    // ⚠️ shown 是**数组**不是数字（模板 wx:for="{{shown}}"）
    shown: [
      { id: 'c1', title: '怎么把一个视频的文案完整提取出来', cat: '使用教程', minutes: 3,
        summary: '从复制链接到拿到文案，完整走一遍。', sections: [{}, {}, {}] },
      { id: 'c2', title: '批量解析怎么用才不浪费额度', cat: '使用教程', minutes: 4,
        summary: '一次 10 条的适用场景与注意事项。', sections: [{}, {}] },
      { id: 'c3', title: '违禁词检测能查出什么', cat: '案例拆解', minutes: 5,
        summary: '四个类目的真实命中案例。', sections: [{}, {}, {}, {}] },
    ],
    total: 3,
    categories: [
      { key: 'all', name: '全部' },
      { key: 'guide', name: '使用教程' },
      { key: 'case', name: '案例拆解' },
      { key: 'update', name: '版本更新' },
    ],
  },

  // ── 文章页 ───────────────────────────────────────────
  article: {
    theme: 'classic',
    loaded: true,
    notFound: false,
    // ⚠️ 正文是 sections 数组（模板 wx:for="{{article.sections}}"），不是 body 字符串
    article: {
      title: '怎么把一个视频的文案完整提取出来',
      cat: '使用教程',
      summary: '从复制链接到拿到文案，完整走一遍。',
      minutes: 3,
      sections: [
        { h: '一、先确认你要的是哪种文案',
          body: '大部分平台的文案就在页面的 meta 信息里，复制链接丢进解析框就能拿到。'
            + '但要注意：能拿到的是公开页面上的文案，不是视频里说的话。' },
        { h: '二、视频里说的话怎么拿',
          body: '那要靠字幕提取。有字幕文件的平台能直接拿，硬字幕的需要 OCR，成本高得多。' },
        { h: '三、拿到之后怎么用',
          body: '别直接照搬。改写一下开头和结尾，保留信息点，去掉原作者的表达习惯。' },
      ],
    },
    p: { prev: null, next: { title: '批量解析怎么用' } },
  },

  // ── 合规说明 ─────────────────────────────────────────
  compliance: {
    theme: 'classic',
    email: 'hi@creatorbox.app',
    hasPhone: false,
    version: '1.2.0',
  },
};

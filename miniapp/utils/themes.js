/**
 * 皮肤系统（M1.5+）
 *
 * 架构：
 *   · 颜色全部收敛到全局样式（CSS 变量：--bg-page / --ink-900 / --brand ...）
 *   · 页面根节点绑定 class="page theme-{{theme}}"，变量随类切换
 *   · 导航栏 / tabBar 用动态 API 实时换色（无需重新编译/发版）
 *   · 当前皮肤存 storage（cb_theme），并在全局数据里同步一份
 *
 * 三套预置：classic（经典橙金）/ dark（午夜暗黑）/ sakura（樱花粉）
 */
const KEYS = ['classic', 'dark', 'sakura', 'jade'];
const STORE_KEY = 'cb_theme';

const THEMES = {
  classic: { name: '琥珀纸感' },
  dark: { name: '曜石黑金' },
  sakura: { name: '樱花粉' },
  jade: { name: '墨绿祖母绿' }
};

/** 导航栏模式：哪些页面是深色 hero（导航随内容走） */
const DARK_NAV_ROUTES = [
  'pages/toolbox/toolbox',
  'pages/ranking/ranking',
  'pages/column/column',
  'pages/article/article'
];

const CHROME = {
  classic: {
    tab: { backgroundColor: '#FFFFFF', color: '#8B7D6E',
           selectedColor: '#D97A26', borderStyle: 'white' },
    navDark: { backgroundColor: '#33210F', frontColor: '#ffffff' },
    navLight: { backgroundColor: '#F7F2EA', frontColor: '#000000' }
  },
  dark: {
    tab: { backgroundColor: '#17171C', color: '#948D84',
           selectedColor: '#D8B98E', borderStyle: 'black' },
    navDark: { backgroundColor: '#17171C', frontColor: '#ffffff' },
    navLight: { backgroundColor: '#0E0E11', frontColor: '#ffffff' }
  },
  sakura: {
    tab: { backgroundColor: '#FFFFFF', color: '#B98A9B',
           selectedColor: '#E85D8F', borderStyle: 'white' },
    navDark: { backgroundColor: '#5C2440', frontColor: '#ffffff' },
    navLight: { backgroundColor: '#FBF6F8', frontColor: '#000000' }
  },
  jade: {
    tab: { backgroundColor: '#121A17', color: '#8A9A93',
           selectedColor: '#6FD3B2', borderStyle: 'black' },
    navDark: { backgroundColor: '#121A17', frontColor: '#ffffff' },
    navLight: { backgroundColor: '#0C1210', frontColor: '#ffffff' }
  }
};

/** 当前皮肤 key（storage → globalData 兜底 classic） */
function current() {
  try {
    const t = wx.getStorageSync(STORE_KEY);
    if (t && KEYS.indexOf(t) >= 0) return t;
  } catch (e) { /* 存储不可用 */ }
  return 'classic';
}

/** 切换皮肤：落库 + 全局同步 + tabBar 立即换色 */
function setTheme(key) {
  if (KEYS.indexOf(key) < 0) return false;
  try { wx.setStorageSync(STORE_KEY, key); } catch (e) { /* 忽略 */ }
  const app = getApp();
  if (app && app.globalData) app.globalData.theme = key;
  applyTabBar(key);
  return true;
}

/** 动态 tabBar 配色 */
function applyTabBar(key) {
  const c = CHROME[key] || CHROME.classic;
  if (wx.setTabBarStyle) wx.setTabBarStyle(c.tab);
}

/**
 * 页面 onShow 调用：同步根节点 theme 类 + 该页导航栏颜色。
 * 页面 wxml 根节点需绑定 class="page theme-{{theme}}"。
 */
function sync(page) {
  const key = current();
  if (page && page.data && page.data.theme !== key) {
    page.setData({ theme: key });
  }
  let route = '';
  try {
    const pages = getCurrentPages();
    route = pages[pages.length - 1].route;
  } catch (e) { /* 非页面环境 */ }
  const c = CHROME[key] || CHROME.classic;
  const isDark = DARK_NAV_ROUTES.indexOf(route) >= 0;
  const nav = isDark ? c.navDark : c.navLight;
  if (wx.setNavigationBarColor) {
    wx.setNavigationBarColor({
      backgroundColor: nav.backgroundColor,
      frontColor: nav.frontColor,
      fail: () => {}     // 某些场景（tab 页刚切入）可能失败，静默
    });
  }
}

module.exports = {
  KEYS, THEMES, THEMES_KEYS: KEYS,
  current, setTheme, sync, applyTabBar
};

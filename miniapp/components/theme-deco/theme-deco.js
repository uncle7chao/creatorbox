/**
 * 皮肤装饰层（M1.5+）
 *
 * 每套皮肤独有的页面氛围层，垫在内容下（z-index:-1）、不挡操作：
 *   classic → 暖光斑（大圆柔光，右上/左下呼吸）
 *   dark    → 星点闪烁 + 顶部辉光
 *   sakura  → 花瓣飘落（循环）
 * 纯 CSS 绘制，无图片资源；随页面 theme 数据实时切换。
 */
Component({
  properties: {
    theme: { type: String, value: 'classic' }
  }
});

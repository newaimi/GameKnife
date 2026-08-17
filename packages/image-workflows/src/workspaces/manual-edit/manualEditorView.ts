/** 像素网格至少放大到单像素约六个屏幕像素时才具有辨识度。 */
export const EDITOR_PIXEL_GRID_MIN_SCALE = 6;

/**
 * 判断手动编辑画布是否显示像素网格。
 * 用户开关控制功能意图，实际倍率控制绘制成本，两项条件需要同时满足。
 */
export function shouldShowEditorPixelGrid(gridVisible: boolean, scale: number) {
  return gridVisible && Number.isFinite(scale) && scale >= EDITOR_PIXEL_GRID_MIN_SCALE;
}

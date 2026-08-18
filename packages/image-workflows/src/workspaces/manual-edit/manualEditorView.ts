/** The pixel grid becomes legible when one image pixel spans roughly six screen pixels. */
export const EDITOR_PIXEL_GRID_MIN_SCALE = 6;

/**
 * Decide whether the manual-edit canvas displays its pixel grid.
 * The user toggle expresses intent and actual scale controls rendering cost, so both conditions must hold.
 */
export function shouldShowEditorPixelGrid(gridVisible: boolean, scale: number) {
  return gridVisible && Number.isFinite(scale) && scale >= EDITOR_PIXEL_GRID_MIN_SCALE;
}

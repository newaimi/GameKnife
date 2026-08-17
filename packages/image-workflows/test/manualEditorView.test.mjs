import assert from "node:assert/strict";
import test from "node:test";
import { EDITOR_PIXEL_GRID_MIN_SCALE, shouldShowEditorPixelGrid } from "../dist/workspaces/manual-edit/manualEditorView.js";

test("手动编辑像素网格只在用户开启且倍率足够时显示", () => {
  assert.equal(shouldShowEditorPixelGrid(false, EDITOR_PIXEL_GRID_MIN_SCALE), false);
  assert.equal(shouldShowEditorPixelGrid(true, EDITOR_PIXEL_GRID_MIN_SCALE - 0.01), false);
  assert.equal(shouldShowEditorPixelGrid(true, EDITOR_PIXEL_GRID_MIN_SCALE), true);
  assert.equal(shouldShowEditorPixelGrid(true, Number.NaN), false);
});

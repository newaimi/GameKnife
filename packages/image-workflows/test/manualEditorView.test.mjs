import assert from "node:assert/strict";
import test from "node:test";
import { EDITOR_PIXEL_GRID_MIN_SCALE, shouldShowEditorPixelGrid } from "../dist/workspaces/manual-edit/manualEditorView.js";

test("manual editor pixel grid requires both the user setting and sufficient zoom", () => {
  assert.equal(shouldShowEditorPixelGrid(false, EDITOR_PIXEL_GRID_MIN_SCALE), false);
  assert.equal(shouldShowEditorPixelGrid(true, EDITOR_PIXEL_GRID_MIN_SCALE - 0.01), false);
  assert.equal(shouldShowEditorPixelGrid(true, EDITOR_PIXEL_GRID_MIN_SCALE), true);
  assert.equal(shouldShowEditorPixelGrid(true, Number.NaN), false);
});

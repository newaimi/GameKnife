import assert from "node:assert/strict";
import test from "node:test";
import { calculateKeyboardPanelWidth, calculatePanelWidth, clampPanelWidth } from "../dist/workbench/panelSizing.js";
import { DEFAULT_WORKSPACE_LAYOUT, readWorkspaceLayoutState } from "../dist/workbench/workspaceLayoutState.js";
import { clampProgressValue } from "../dist/feedback/feedback.js";
import { parseThemeMode } from "../dist/theme/theme.js";

test("clampPanelWidth keeps the width inside the configured range", () => {
  assert.equal(clampPanelWidth(120, 176, 320), 176);
  assert.equal(clampPanelWidth(240, 176, 320), 240);
  assert.equal(clampPanelWidth(480, 176, 320), 320);
});

test("calculatePanelWidth follows the physical edge for both sides", () => {
  assert.equal(calculatePanelWidth({ side: "left", startWidth: 220, startPointer: 100, currentPointer: 132, min: 176, max: 320 }), 252);
  assert.equal(calculatePanelWidth({ side: "right", startWidth: 320, startPointer: 500, currentPointer: 468, min: 260, max: 440 }), 352);
});

test("calculateKeyboardPanelWidth uses Home, End and directional arrows", () => {
  assert.equal(calculateKeyboardPanelWidth({ side: "left", width: 220, key: "ArrowRight", min: 176, max: 320 }), 236);
  assert.equal(calculateKeyboardPanelWidth({ side: "right", width: 320, key: "ArrowLeft", min: 260, max: 440 }), 336);
  assert.equal(calculateKeyboardPanelWidth({ side: "left", width: 220, key: "Home", min: 176, max: 320 }), 176);
  assert.equal(calculateKeyboardPanelWidth({ side: "right", width: 320, key: "End", min: 260, max: 440 }), 440);
});

test("readWorkspaceLayoutState returns defaults for missing or invalid data", () => {
  assert.deepEqual(readWorkspaceLayoutState(null), DEFAULT_WORKSPACE_LAYOUT);
  assert.deepEqual(readWorkspaceLayoutState("{"), DEFAULT_WORKSPACE_LAYOUT);
});

test("readWorkspaceLayoutState restores valid preferences and clamps widths", () => {
  assert.deepEqual(
    readWorkspaceLayoutState(JSON.stringify({ leftWidth: 900, rightWidth: 100, leftCollapsed: true, rightCollapsed: false })),
    { leftWidth: 320, rightWidth: 260, leftCollapsed: true, rightCollapsed: false },
  );
});

test("readWorkspaceLayoutState ignores incompatible legacy fields", () => {
  assert.deepEqual(readWorkspaceLayoutState(JSON.stringify({ leftWidth: "wide", rightCollapsed: "yes" })), DEFAULT_WORKSPACE_LAYOUT);
});

test("clampProgressValue normalizes invalid and out-of-range progress", () => {
  assert.equal(clampProgressValue(Number.NaN), 0);
  assert.equal(clampProgressValue(-12), 0);
  assert.equal(clampProgressValue(41.6), 42);
  assert.equal(clampProgressValue(180), 100);
});

test("parseThemeMode keeps saved themes and defaults to dark", () => {
  assert.equal(parseThemeMode("light"), "light");
  assert.equal(parseThemeMode("dark"), "dark");
  assert.equal(parseThemeMode("system"), "dark");
  assert.equal(parseThemeMode(null), "dark");
});

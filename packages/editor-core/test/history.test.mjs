import assert from "node:assert/strict";
import test from "node:test";

class ImageDataPolyfill {
  constructor(dataOrWidth, widthOrHeight, maybeHeight) {
    if (typeof dataOrWidth === "number") {
      this.width = dataOrWidth;
      this.height = widthOrHeight;
      this.data = new Uint8ClampedArray(this.width * this.height * 4);
      return;
    }
    this.data = dataOrWidth;
    this.width = widthOrHeight;
    this.height = maybeHeight;
  }
}

globalThis.ImageData = ImageDataPolyfill;

const {
  applyEditorHistoryEntry,
  buildEditorStrokeHistoryStates,
  captureEditorPixelHistoryState,
  captureEditorSelectionHistoryState,
  cloneEditorSnapshot,
  compositeEditorDocument,
  compositeEditorDocumentRegion,
  createEditorPixelRecorder,
  drawEditorBrush,
  estimateEditorHistoryBytes,
  expandEditorPixelHistoryState,
  extractSelectionClipboard,
  pasteFloatingSelection,
} = await import("../dist/index.js");

function createDocument(width, height) {
  const originalImageData = new ImageData(width, height);
  const imageData = new ImageData(width, height);
  return {
    name: "Test image",
    width,
    height,
    layers: [{ id: "layer-1", name: "Original", visible: true, opacity: 100, imageData }],
    activeLayerId: "layer-1",
    originalImageData,
    selection: null,
    floatingSelection: null,
    dirty: false,
  };
}

test("structural snapshots share the read-only source and isolate editable layers", () => {
  const doc = createDocument(8, 8);
  doc.layers[0].imageData.data[0] = 20;
  const snapshot = cloneEditorSnapshot(doc, "Before structural operation");

  assert.equal(snapshot.originalImageData, doc.originalImageData);
  assert.notEqual(snapshot.layers[0].imageData, doc.layers[0].imageData);
  doc.layers[0].imageData.data[0] = 180;
  assert.equal(snapshot.layers[0].imageData.data[0], 20);
});

test("large-image selection history does not retain layer or source pixels", () => {
  const doc = createDocument(2048, 2048);
  const before = captureEditorSelectionHistoryState(doc);
  doc.selection = {
    kind: "rect",
    bounds: { x: 100, y: 100, width: 64, height: 64 },
    mask: new Uint8ClampedArray(0),
  };
  const after = captureEditorSelectionHistoryState(doc);
  const entry = {
    id: "history-selection",
    title: "Rectangle selection",
    createdAt: 1,
    redrawBitmap: false,
    layout: false,
    kind: "selection",
    before,
    after,
  };

  assert.equal(estimateEditorHistoryBytes([entry]), 0);
  assert.equal("pixels" in before, false);
  assert.equal("layers" in before, false);
});

test("large-image strokes retain only changed regions and support isolated undo and redo", () => {
  const doc = createDocument(2048, 2048);
  const beforeSelection = captureEditorSelectionHistoryState(doc);
  const recorder = createEditorPixelRecorder("layer-1", doc.width, doc.height);
  const stroke = { pointerId: 1, recorder, beforeSelection };

  drawEditorBrush(doc, { x: 1024, y: 1024 }, "brush", {
    size: 3,
    hardness: 100,
    opacity: 100,
    color: "#ff0000",
    hardEraser: true,
  }, stroke);
  const states = buildEditorStrokeHistoryStates(doc, recorder, beforeSelection);
  assert.ok(states);
  assert.ok(states.bounds.width <= 5);
  assert.ok(states.bounds.height <= 5);

  const entry = {
    id: "history-1",
    title: "Brush",
    createdAt: 1,
    redrawBitmap: true,
    layout: false,
    kind: "pixels",
    ...states,
  };
  assert.ok(estimateEditorHistoryBytes([entry]) < 1024);

  applyEditorHistoryEntry(doc, entry, "before");
  assert.equal(doc.layers[0].imageData.data[(1024 * doc.width + 1024) * 4 + 3], 0);
  applyEditorHistoryEntry(doc, entry, "after");
  assert.equal(doc.layers[0].imageData.data[(1024 * doc.width + 1024) * 4], 255);
});

test("strokes without pixel changes do not create history state", () => {
  const doc = createDocument(16, 16);
  const beforeSelection = captureEditorSelectionHistoryState(doc);
  const recorder = createEditorPixelRecorder("layer-1", doc.width, doc.height);
  drawEditorBrush(doc, { x: 8, y: 8 }, "restore", {
    size: 4,
    hardness: 100,
    opacity: 100,
    color: "#000000",
    hardEraser: true,
  }, { pointerId: 1, recorder, beforeSelection });

  assert.equal(buildEditorStrokeHistoryStates(doc, recorder, beforeSelection), null);
});

test("moving a selection uses the union of source and target regions for undo and redo", () => {
  const doc = createDocument(6, 2);
  const sourceIndex = (0 * doc.width + 1) * 4;
  const targetIndex = (0 * doc.width + 4) * 4;
  doc.layers[0].imageData.data.set([240, 60, 20, 255], sourceIndex);
  doc.selection = {
    kind: "rect",
    bounds: { x: 1, y: 0, width: 1, height: 1 },
    mask: new Uint8ClampedArray(0),
  };
  const initialBounds = { ...doc.selection.bounds };
  const before = captureEditorPixelHistoryState(doc, "layer-1", initialBounds);
  assert.ok(before);
  doc.floatingSelection = extractSelectionClipboard(doc, true);
  doc.selection = null;
  doc.floatingSelection.bounds = { x: 4, y: 0, width: 1, height: 1 };

  const expanded = expandEditorPixelHistoryState(doc, "layer-1", initialBounds, before, doc.floatingSelection.bounds);
  assert.ok(expanded);
  pasteFloatingSelection(doc);
  const after = captureEditorPixelHistoryState(doc, "layer-1", expanded.bounds);
  assert.ok(after);
  const entry = {
    id: "history-move",
    title: "Move selection",
    createdAt: 1,
    redrawBitmap: true,
    layout: false,
    kind: "pixels",
    layerId: "layer-1",
    bounds: expanded.bounds,
    before: expanded.before,
    after,
  };

  applyEditorHistoryEntry(doc, entry, "before");
  assert.deepEqual([...doc.layers[0].imageData.data.slice(sourceIndex, sourceIndex + 4)], [240, 60, 20, 255]);
  assert.equal(doc.layers[0].imageData.data[targetIndex + 3], 0);
  assert.ok(doc.selection);

  applyEditorHistoryEntry(doc, entry, "after");
  assert.equal(doc.layers[0].imageData.data[sourceIndex + 3], 0);
  assert.deepEqual([...doc.layers[0].imageData.data.slice(targetIndex, targetIndex + 4)], [240, 60, 20, 255]);
  assert.equal(doc.selection, null);
});

test("regional composition matches the corresponding full-document region", () => {
  const doc = createDocument(5, 4);
  doc.layers[0].imageData.data.fill(0);
  for (let index = 0; index < doc.layers[0].imageData.data.length; index += 4) {
    doc.layers[0].imageData.data[index] = 10;
    doc.layers[0].imageData.data[index + 3] = 255;
  }
  const upper = new ImageData(5, 4);
  upper.data.set([200, 50, 10, 128], (1 * 5 + 2) * 4);
  doc.layers.push({ id: "layer-2", name: "Upper layer", visible: true, opacity: 80, imageData: upper });
  const floating = new ImageData(2, 1);
  floating.data.set([20, 220, 40, 255, 20, 220, 40, 255]);
  doc.floatingSelection = { name: "Floating selection", imageData: floating, bounds: { x: 3, y: 2, width: 2, height: 1 } };

  const bounds = { x: 1, y: 1, width: 4, height: 2 };
  const full = compositeEditorDocument(doc);
  const region = compositeEditorDocumentRegion(doc, bounds);
  for (let y = 0; y < bounds.height; y += 1) {
    const sourceStart = ((bounds.y + y) * doc.width + bounds.x) * 4;
    const targetStart = y * bounds.width * 4;
    assert.deepEqual(
      [...region.data.slice(targetStart, targetStart + bounds.width * 4)],
      [...full.data.slice(sourceStart, sourceStart + bounds.width * 4)],
    );
  }
});

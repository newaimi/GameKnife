import type {
  EditorClipboardItem,
  EditorDocument,
  EditorHistoryEntry,
  EditorLayer,
  EditorLayerHistoryState,
  EditorPixelHistoryState,
  EditorPixelRecorder,
  EditorSelection,
  EditorSelectionHistoryState,
  EditorSelectionMask,
  EditorSnapshot,
} from "./types.js";

/** 生成只在当前编辑会话内使用的稳定标识。 */
export function createEditorId(prefix: string) {
  return `${prefix}_${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}_${Math.random().toString(16).slice(2)}`}`;
}

/** 复制像素缓冲，保证历史记录不会被后续原地绘制污染。 */
export function cloneImageData(imageData: ImageData) {
  return new ImageData(new Uint8ClampedArray(imageData.data), imageData.width, imageData.height);
}

/** 复制图层属性和像素，用于确实改变图层结构或画布尺寸的历史节点。 */
export function cloneEditorLayer(layer: EditorLayer): EditorLayer {
  return { ...layer, imageData: cloneImageData(layer.imageData) };
}

/** 复制选区 mask 和路径，拖动中的选区不会回写到已经提交的历史状态。 */
export function cloneSelectionMask(selection: EditorSelectionMask | null): EditorSelectionMask | null {
  if (!selection) return null;
  return {
    ...selection,
    bounds: { ...selection.bounds },
    mask: selection.kind === "rect" ? new Uint8ClampedArray(0) : new Uint8ClampedArray(selection.mask),
    path: selection.path ? selection.path.map((point) => ({ ...point })) : undefined,
  };
}

/** 复制浮动选区。它只包含局部像素，允许在轻量选区历史中独立恢复。 */
export function cloneEditorClipboardItem(item: EditorClipboardItem): EditorClipboardItem {
  return { name: item.name, imageData: cloneImageData(item.imageData), bounds: { ...item.bounds } };
}

/**
 * 创建结构快照。原始图片在编辑会话内只读，直接共享引用；图层像素仍需复制，
 * 因为画笔和修边操作会原地修改当前图层。
 */
export function cloneEditorSnapshot(doc: EditorDocument, title: string): EditorSnapshot {
  return {
    id: createEditorId("snapshot"),
    title,
    createdAt: Date.now(),
    width: doc.width,
    height: doc.height,
    originalImageData: doc.originalImageData,
    layers: doc.layers.map(cloneEditorLayer),
    activeLayerId: doc.activeLayerId,
    selection: cloneSelectionMask(doc.selection),
    floatingSelection: doc.floatingSelection ? cloneEditorClipboardItem(doc.floatingSelection) : null,
  };
}

/** 恢复结构快照；恢复后的可编辑图层重新复制，历史节点继续保持只读。 */
export function restoreEditorSnapshot(doc: EditorDocument, snapshot: EditorSnapshot) {
  doc.width = snapshot.width;
  doc.height = snapshot.height;
  doc.layers = snapshot.layers.map(cloneEditorLayer);
  doc.activeLayerId = snapshot.activeLayerId;
  doc.selection = cloneSelectionMask(snapshot.selection);
  doc.floatingSelection = snapshot.floatingSelection ? cloneEditorClipboardItem(snapshot.floatingSelection) : null;
  doc.originalImageData = snapshot.originalImageData;
}

/** 捕获只影响选区的状态，避免矩形、套索和魔棒复制整张图片。 */
export function captureEditorSelectionHistoryState(doc: EditorDocument): EditorSelectionHistoryState {
  return {
    activeLayerId: doc.activeLayerId,
    selection: cloneSelectionMask(doc.selection),
    floatingSelection: doc.floatingSelection ? cloneEditorClipboardItem(doc.floatingSelection) : null,
  };
}

/** 捕获图层顺序和展示属性，重命名、显隐和透明度调整不保存图层像素。 */
export function captureEditorLayerHistoryState(doc: EditorDocument): EditorLayerHistoryState {
  return {
    activeLayerId: doc.activeLayerId,
    layers: doc.layers.map(({ id, name, visible, opacity }) => ({ id, name, visible, opacity })),
  };
}

/** 从图层读取一个独立的矩形像素块。 */
export function readEditorImageDataPatch(imageData: ImageData, bounds: EditorSelection): ImageData {
  const safeBounds = normalizeHistoryBounds(bounds, imageData.width, imageData.height);
  const patch = new ImageData(safeBounds.width, safeBounds.height);
  for (let y = 0; y < safeBounds.height; y += 1) {
    const sourceStart = ((safeBounds.y + y) * imageData.width + safeBounds.x) * 4;
    const targetStart = y * safeBounds.width * 4;
    patch.data.set(imageData.data.subarray(sourceStart, sourceStart + safeBounds.width * 4), targetStart);
  }
  return patch;
}

/** 把历史像素块写回目标图层；边界来自同一文档版本，写入时仍做裁剪以避免异常历史破坏缓冲区。 */
export function writeEditorImageDataPatch(target: ImageData, patch: ImageData, bounds: EditorSelection) {
  const safeBounds = normalizeHistoryBounds(bounds, target.width, target.height);
  const rows = Math.min(safeBounds.height, patch.height);
  const columns = Math.min(safeBounds.width, patch.width);
  for (let y = 0; y < rows; y += 1) {
    const sourceStart = y * patch.width * 4;
    const targetStart = ((safeBounds.y + y) * target.width + safeBounds.x) * 4;
    target.data.set(patch.data.subarray(sourceStart, sourceStart + columns * 4), targetStart);
  }
}

/** 捕获已知脏区的像素和选区状态，适用于删除、剪切、贴入和整层修边。 */
export function captureEditorPixelHistoryState(doc: EditorDocument, layerId: string, bounds: EditorSelection): EditorPixelHistoryState | null {
  const layer = doc.layers.find((item) => item.id === layerId);
  if (!layer) return null;
  return {
    ...captureEditorSelectionHistoryState(doc),
    pixels: readEditorImageDataPatch(layer.imageData, bounds),
  };
}

/** 创建笔画记录器，绘制时只记住第一次碰到某个像素之前的 RGBA。 */
export function createEditorPixelRecorder(layerId: string, width: number, height: number): EditorPixelRecorder {
  return {
    layerId,
    width,
    height,
    minX: width,
    minY: height,
    maxX: -1,
    maxY: -1,
    beforePixels: new Map(),
  };
}

/** 在修改像素前保存其原值；同一笔画重复经过该像素时只记录一次。 */
export function recordEditorPixelBefore(recorder: EditorPixelRecorder, data: Uint8ClampedArray, byteIndex: number) {
  const pixelIndex = Math.floor(byteIndex / 4);
  if (recorder.beforePixels.has(pixelIndex)) return;
  const x = pixelIndex % recorder.width;
  const y = Math.floor(pixelIndex / recorder.width);
  const packed = data[byteIndex] + data[byteIndex + 1] * 256 + data[byteIndex + 2] * 65536 + data[byteIndex + 3] * 16777216;
  recorder.beforePixels.set(pixelIndex, packed);
  recorder.minX = Math.min(recorder.minX, x);
  recorder.minY = Math.min(recorder.minY, y);
  recorder.maxX = Math.max(recorder.maxX, x);
  recorder.maxY = Math.max(recorder.maxY, y);
}

/**
 * 把笔画期间的稀疏像素记录压缩成前后两个矩形块。
 * 矩形内没有被笔画碰到的像素沿用当前值，撤销时不会影响邻近内容。
 */
export function buildEditorStrokeHistoryStates(
  doc: EditorDocument,
  recorder: EditorPixelRecorder,
  beforeSelection: EditorSelectionHistoryState,
): { layerId: string; bounds: EditorSelection; before: EditorPixelHistoryState; after: EditorPixelHistoryState } | null {
  const layer = doc.layers.find((item) => item.id === recorder.layerId);
  if (!layer || recorder.maxX < recorder.minX || recorder.maxY < recorder.minY) return null;
  const bounds = {
    x: recorder.minX,
    y: recorder.minY,
    width: recorder.maxX - recorder.minX + 1,
    height: recorder.maxY - recorder.minY + 1,
  };
  const afterPixels = readEditorImageDataPatch(layer.imageData, bounds);
  const beforePixels = cloneImageData(afterPixels);
  for (const [pixelIndex, packed] of recorder.beforePixels) {
    const x = pixelIndex % recorder.width;
    const y = Math.floor(pixelIndex / recorder.width);
    const localIndex = ((y - bounds.y) * bounds.width + x - bounds.x) * 4;
    beforePixels.data[localIndex] = packed % 256;
    beforePixels.data[localIndex + 1] = Math.floor(packed / 256) % 256;
    beforePixels.data[localIndex + 2] = Math.floor(packed / 65536) % 256;
    beforePixels.data[localIndex + 3] = Math.floor(packed / 16777216) % 256;
  }
  // 恢复笔扫过未修改区域、画笔使用相同颜色时不应产生空历史，避免占用撤销次数。
  if (areImageDataEqual(beforePixels, afterPixels)) return null;
  return {
    layerId: recorder.layerId,
    bounds,
    before: { ...cloneEditorSelectionHistoryState(beforeSelection), pixels: beforePixels },
    after: { ...captureEditorSelectionHistoryState(doc), pixels: afterPixels },
  };
}

/** 合并两个脏区，增量重绘和移动选区历史使用同一边界口径。 */
export function unionEditorBounds(first: EditorSelection, second: EditorSelection): EditorSelection {
  const x = Math.min(first.x, second.x);
  const y = Math.min(first.y, second.y);
  const right = Math.max(first.x + first.width, second.x + second.width);
  const bottom = Math.max(first.y + first.height, second.y + second.height);
  return { x, y, width: right - x, height: bottom - y };
}

/**
 * 移动选区在开始和结束时脏区不同。该方法用移动前的局部像素覆盖当前临时状态，
 * 还原出完整联合区域在操作前的像素，避免为未知终点提前复制整层。
 */
export function expandEditorPixelHistoryState(
  doc: EditorDocument,
  layerId: string,
  previousBounds: EditorSelection,
  previous: EditorPixelHistoryState,
  nextBounds: EditorSelection,
): { bounds: EditorSelection; before: EditorPixelHistoryState } | null {
  const layer = doc.layers.find((item) => item.id === layerId);
  if (!layer) return null;
  const bounds = normalizeHistoryBounds(unionEditorBounds(previousBounds, nextBounds), layer.imageData.width, layer.imageData.height);
  const safePreviousBounds = normalizeHistoryBounds(previousBounds, layer.imageData.width, layer.imageData.height);
  const pixels = readEditorImageDataPatch(layer.imageData, bounds);
  copyPatchIntoPatch(pixels, previous.pixels, safePreviousBounds.x - bounds.x, safePreviousBounds.y - bounds.y);
  return {
    bounds,
    before: { ...cloneEditorSelectionHistoryState(previous), pixels },
  };
}

/** 根据历史记录类型恢复前态或后态。 */
export function applyEditorHistoryEntry(doc: EditorDocument, entry: EditorHistoryEntry, direction: "before" | "after") {
  const state = entry[direction];
  if (entry.kind === "snapshot") {
    restoreEditorSnapshot(doc, state as EditorSnapshot);
    return;
  }
  if (entry.kind === "selection") {
    applyEditorSelectionHistoryState(doc, state as EditorSelectionHistoryState);
    return;
  }
  if (entry.kind === "layers") {
    applyEditorLayerHistoryState(doc, state as EditorLayerHistoryState);
    return;
  }
  const pixelState = state as EditorPixelHistoryState;
  const layer = doc.layers.find((item) => item.id === entry.layerId);
  if (layer) writeEditorImageDataPatch(layer.imageData, pixelState.pixels, entry.bounds);
  applyEditorSelectionHistoryState(doc, pixelState);
}

/** 按真实唯一缓冲区估算历史内存，共享的原图引用在同一历史集合中只计算一次。 */
export function estimateEditorHistoryBytes(entries: EditorHistoryEntry[]) {
  const buffers = new Set<ArrayBufferLike>();
  const addImage = (imageData: ImageData | null | undefined) => {
    if (imageData) buffers.add(imageData.data.buffer);
  };
  const addSelection = (state: EditorSelectionHistoryState) => {
    if (state.selection) buffers.add(state.selection.mask.buffer);
    addImage(state.floatingSelection?.imageData);
  };
  for (const entry of entries) {
    if (entry.kind === "snapshot") {
      for (const snapshot of [entry.before, entry.after]) {
        addImage(snapshot.originalImageData);
        snapshot.layers.forEach((layer) => addImage(layer.imageData));
        if (snapshot.selection) buffers.add(snapshot.selection.mask.buffer);
        addImage(snapshot.floatingSelection?.imageData);
      }
      continue;
    }
    if (entry.kind === "selection") {
      addSelection(entry.before);
      addSelection(entry.after);
      continue;
    }
    if (entry.kind === "pixels") {
      addImage(entry.before.pixels);
      addImage(entry.after.pixels);
      addSelection(entry.before);
      addSelection(entry.after);
    }
  }
  let bytes = 0;
  for (const buffer of buffers) bytes += buffer.byteLength;
  return bytes;
}

function cloneEditorSelectionHistoryState(state: EditorSelectionHistoryState): EditorSelectionHistoryState {
  return {
    activeLayerId: state.activeLayerId,
    selection: cloneSelectionMask(state.selection),
    floatingSelection: state.floatingSelection ? cloneEditorClipboardItem(state.floatingSelection) : null,
  };
}

function applyEditorSelectionHistoryState(doc: EditorDocument, state: EditorSelectionHistoryState) {
  doc.activeLayerId = state.activeLayerId;
  doc.selection = cloneSelectionMask(state.selection);
  doc.floatingSelection = state.floatingSelection ? cloneEditorClipboardItem(state.floatingSelection) : null;
}

function applyEditorLayerHistoryState(doc: EditorDocument, state: EditorLayerHistoryState) {
  const currentLayers = new Map(doc.layers.map((layer) => [layer.id, layer]));
  const restoredLayers: EditorLayer[] = [];
  for (const item of state.layers) {
    const layer = currentLayers.get(item.id);
    if (layer) restoredLayers.push({ ...layer, name: item.name, visible: item.visible, opacity: item.opacity });
  }
  if (restoredLayers.length === doc.layers.length) doc.layers = restoredLayers;
  doc.activeLayerId = state.activeLayerId;
}

function copyPatchIntoPatch(target: ImageData, source: ImageData, left: number, top: number) {
  for (let y = 0; y < source.height; y += 1) {
    if (top + y < 0 || top + y >= target.height) continue;
    const sourceLeft = Math.max(0, -left);
    const targetLeft = Math.max(0, left);
    const columns = Math.min(source.width - sourceLeft, target.width - targetLeft);
    if (columns <= 0) continue;
    const sourceStart = (y * source.width + sourceLeft) * 4;
    const targetStart = ((top + y) * target.width + targetLeft) * 4;
    target.data.set(source.data.subarray(sourceStart, sourceStart + columns * 4), targetStart);
  }
}

function areImageDataEqual(first: ImageData, second: ImageData) {
  if (first.width !== second.width || first.height !== second.height) return false;
  for (let index = 0; index < first.data.length; index += 1) {
    if (first.data[index] !== second.data[index]) return false;
  }
  return true;
}

function normalizeHistoryBounds(bounds: EditorSelection, width: number, height: number): EditorSelection {
  const x = Math.max(0, Math.min(width - 1, Math.floor(bounds.x)));
  const y = Math.max(0, Math.min(height - 1, Math.floor(bounds.y)));
  const right = Math.max(x + 1, Math.min(width, Math.ceil(bounds.x + bounds.width)));
  const bottom = Math.max(y + 1, Math.min(height, Math.ceil(bounds.y + bounds.height)));
  return { x, y, width: right - x, height: bottom - y };
}

import type {
  EditorBrushSettings,
  EditorClipboardItem,
  EditorDocument,
  EditorExportOptions,
  EditorHistoryEntry,
  EditorLayer,
  EditorSelection,
  EditorSelectionMask,
  EditorSnapshot,
  EditorTool,
  EditorZoomPreviewMode,
} from "./types.js";
import { clamp } from "./math.js";
import { cloneImageData, createEditorId, recordEditorPixelBefore } from "./history.js";
import type { EditorLassoDraft, EditorSelectionDraft, EditorStatus, EditorStrokeState, ImagePoint } from "./types.js";

export function renderEditorCanvas(
  canvas: HTMLCanvasElement | null,
  overlay: HTMLCanvasElement | null,
  doc: EditorDocument | null,
  pointer: ImagePoint | null,
  brush: EditorBrushSettings,
  tool: EditorTool,
  zoomPreviewMode: EditorZoomPreviewMode,
  lassoDraft: EditorLassoDraft | null,
  redrawBitmap = true,
  bitmapBounds?: EditorSelection,
) {
  if (!canvas || !overlay || !doc) return;
  if (canvas.width !== doc.width || canvas.height !== doc.height) {
    canvas.width = doc.width;
    canvas.height = doc.height;
  }
  if (overlay.width !== doc.width || overlay.height !== doc.height) {
    overlay.width = doc.width;
    overlay.height = doc.height;
  }

  const context = canvas.getContext("2d", { willReadFrequently: true });
  const overlayContext = overlay.getContext("2d");
  if (!context || !overlayContext) return;
  context.imageSmoothingEnabled = false;
  if (redrawBitmap) {
    if (bitmapBounds) {
      const safeBounds = normalizeEditorBounds(
        bitmapBounds.x,
        bitmapBounds.y,
        bitmapBounds.x + bitmapBounds.width,
        bitmapBounds.y + bitmapBounds.height,
        doc.width,
        doc.height,
      );
      if (safeBounds) context.putImageData(compositeEditorDocumentRegion(doc, safeBounds), safeBounds.x, safeBounds.y);
    } else {
      context.putImageData(compositeEditorDocument(doc), 0, 0);
    }
  }

  overlayContext.clearRect(0, 0, doc.width, doc.height);
  overlayContext.imageSmoothingEnabled = false;
  if (doc.selection) {
    drawEditorSelection(overlayContext, doc.selection);
  }
  if (doc.floatingSelection) {
    drawFloatingSelection(overlayContext, doc.floatingSelection);
  }
  if (lassoDraft) {
    drawEditorLassoDraft(overlayContext, lassoDraft.path);
  }
  if (pointer && tool !== "pan" && tool !== "rect-selection" && tool !== "lasso-selection" && tool !== "magic-wand" && tool !== "move-selection") {
    drawEditorPointer(overlayContext, pointer, brush, tool);
  }
  if (pointer && zoomPreviewMode !== "off") {
    drawEditorZoomPreview(overlayContext, canvas, pointer, zoomPreviewMode);
  }
}

export function drawEditorSelection(context: CanvasRenderingContext2D, selection: EditorSelectionMask) {
  context.save();
  if (selection.kind === "rect") {
    context.fillStyle = "rgba(23, 103, 255, 0.12)";
    context.fillRect(selection.bounds.x, selection.bounds.y, selection.bounds.width, selection.bounds.height);
  } else {
    const maskOverlay = context.createImageData(selection.bounds.width, selection.bounds.height);
    for (let y = 0; y < selection.bounds.height; y += 1) {
      for (let x = 0; x < selection.bounds.width; x += 1) {
        const sourceX = selection.bounds.x + x;
        const sourceY = selection.bounds.y + y;
        if (!selection.mask[sourceY * context.canvas.width + sourceX]) continue;
        const dataIndex = (y * selection.bounds.width + x) * 4;
        maskOverlay.data[dataIndex] = 23;
        maskOverlay.data[dataIndex + 1] = 103;
        maskOverlay.data[dataIndex + 2] = 255;
        maskOverlay.data[dataIndex + 3] = 30;
      }
    }
    context.putImageData(maskOverlay, selection.bounds.x, selection.bounds.y);
  }
  context.strokeStyle = "rgba(23, 103, 255, 0.95)";
  context.lineWidth = 1;
  context.setLineDash([4, 3]);
  context.strokeRect(selection.bounds.x + 0.5, selection.bounds.y + 0.5, Math.max(0, selection.bounds.width - 1), Math.max(0, selection.bounds.height - 1));
  context.restore();
}

export function drawFloatingSelection(context: CanvasRenderingContext2D, item: EditorClipboardItem) {
  context.save();
  context.strokeStyle = "rgba(245, 158, 11, 0.96)";
  context.lineWidth = 1;
  context.setLineDash([3, 3]);
  context.strokeRect(item.bounds.x + 0.5, item.bounds.y + 0.5, Math.max(0, item.bounds.width - 1), Math.max(0, item.bounds.height - 1));
  context.restore();
}

export function drawEditorLassoDraft(context: CanvasRenderingContext2D, path: ImagePoint[]) {
  if (path.length < 2) return;
  context.save();
  context.strokeStyle = "rgba(23, 103, 255, 0.95)";
  context.lineWidth = 1;
  context.setLineDash([3, 3]);
  context.beginPath();
  context.moveTo(path[0].x, path[0].y);
  for (const point of path.slice(1)) context.lineTo(point.x, point.y);
  context.stroke();
  context.restore();
}

export function drawEditorZoomPreview(context: CanvasRenderingContext2D, sourceCanvas: HTMLCanvasElement, pointer: ImagePoint, mode: EditorZoomPreviewMode) {
  const drawWindow = (left: number, top: number, size: number) => {
    const sampleSize = 18;
    const cellSize = 5;
    const centerX = Math.floor(pointer.x);
    const centerY = Math.floor(pointer.y);
    const sourceWidth = Math.min(sampleSize, sourceCanvas.width);
    const sourceHeight = Math.min(sampleSize, sourceCanvas.height);
    const sourceLeft = Math.floor(clamp(centerX - Math.floor(sourceWidth / 2), 0, Math.max(0, sourceCanvas.width - sourceWidth)));
    const sourceTop = Math.floor(clamp(centerY - Math.floor(sourceHeight / 2), 0, Math.max(0, sourceCanvas.height - sourceHeight)));
    context.save();
    context.fillStyle = "rgba(255, 255, 255, 0.92)";
    context.strokeStyle = "rgba(23, 103, 255, 0.9)";
    context.lineWidth = 1;
    context.beginPath();
    context.roundRect(left, top, size, size, 8);
    context.fill();
    context.stroke();
    context.imageSmoothingEnabled = false;
    context.drawImage(sourceCanvas, sourceLeft, sourceTop, sourceWidth, sourceHeight, left + 8, top + 8, sourceWidth * cellSize, sourceHeight * cellSize);
    context.strokeStyle = "rgba(23, 103, 255, 0.52)";
    context.strokeRect(left + 8 + Math.floor(sourceWidth / 2) * cellSize, top + 8 + Math.floor(sourceHeight / 2) * cellSize, cellSize, cellSize);
    context.restore();
  };

  if (mode === "loupe" || mode === "both") {
    drawWindow(clamp(pointer.x + 18, 0, Math.max(0, sourceCanvas.width - 106)), clamp(pointer.y + 18, 0, Math.max(0, sourceCanvas.height - 106)), 106);
  }
  if (mode === "panel" || mode === "both") {
    drawWindow(10, 10, 106);
  }
}

export function drawEditorPointer(context: CanvasRenderingContext2D, pointer: ImagePoint, brush: EditorBrushSettings, tool: EditorTool) {
  const radius = Math.max(0.5, brush.size / 2);
  context.save();
  context.strokeStyle = tool === "eraser" ? "rgba(239, 68, 68, 0.92)" : tool === "restore" ? "rgba(34, 197, 94, 0.92)" : "rgba(23, 103, 255, 0.92)";
  context.lineWidth = 1;
  context.beginPath();
  context.arc(pointer.x, pointer.y, radius, 0, Math.PI * 2);
  context.stroke();
  context.restore();
}

export function readEditorStatus(
  doc: EditorDocument | null,
  history: EditorHistoryEntry[],
  redoStack: EditorHistoryEntry[],
  snapshots: EditorSnapshot[],
  pointer: ImagePoint | null,
): EditorStatus {
  if (!doc) {
    return {
      width: 0,
      height: 0,
      canUndo: false,
      canRedo: false,
      dirty: false,
      hasSelection: false,
      hasFloatingSelection: false,
      sample: "-",
      layers: [],
      history: [],
      snapshots: [],
      activeLayerId: null,
    };
  }
  return {
    width: doc.width,
    height: doc.height,
    canUndo: history.length > 0,
    canRedo: redoStack.length > 0,
    dirty: doc.dirty,
    hasSelection: Boolean(doc.selection),
    hasFloatingSelection: Boolean(doc.floatingSelection),
    sample: pointer ? readEditorDocumentSample(doc, pointer) : "RGBA -",
    layers: [...doc.layers].reverse().map((layer) => ({
      id: layer.id,
      name: layer.name,
      visible: layer.visible,
      opacity: layer.opacity,
      active: layer.id === doc.activeLayerId,
    })),
    history: history.map(({ id, title, createdAt }) => ({ id, title, createdAt })),
    snapshots: snapshots.map(({ id, title, createdAt }) => ({ id, title, createdAt })),
    activeLayerId: doc.activeLayerId,
  };
}

export function createBlankEditorLayer(width: number, height: number, name: string): EditorLayer {
  return { id: createEditorId("layer"), name, visible: true, opacity: 100, imageData: new ImageData(width, height) };
}

export function getActiveEditorLayer(doc: EditorDocument) {
  return doc.layers.find((layer) => layer.id === doc.activeLayerId) ?? doc.layers[0] ?? null;
}

export function compositeEditorDocument(doc: EditorDocument) {
  // 编辑器内部按图层保存像素，真正预览和导出时才合成。
  // 这样图层显隐、透明度和顺序调整不会破坏原始图层数据，也方便撤销回退。
  const flattened = compositeEditorLayers(doc.width, doc.height, doc.layers);
  if (doc.floatingSelection) {
    pasteImageDataWithAlpha(flattened, doc.floatingSelection.imageData, doc.floatingSelection.bounds.x, doc.floatingSelection.bounds.y);
  }
  return flattened;
}

/**
 * 只合成需要刷新的文档区域。画笔和移动选区把该结果写回主 canvas 的对应位置，
 * 拖动过程中无需为未变化的像素创建和遍历全尺寸缓冲区。
 */
export function compositeEditorDocumentRegion(doc: EditorDocument, bounds: EditorSelection) {
  const safeBounds = normalizeEditorBounds(bounds.x, bounds.y, bounds.x + bounds.width, bounds.y + bounds.height, doc.width, doc.height);
  if (!safeBounds) return new ImageData(1, 1);
  const output = new ImageData(safeBounds.width, safeBounds.height);
  for (const layer of doc.layers) {
    if (!layer.visible || layer.opacity <= 0) continue;
    blendImageDataRegionOver(output, layer.imageData, layer.opacity / 100, 0, 0, safeBounds);
  }
  if (doc.floatingSelection) {
    blendImageDataRegionOver(
      output,
      doc.floatingSelection.imageData,
      1,
      doc.floatingSelection.bounds.x,
      doc.floatingSelection.bounds.y,
      safeBounds,
    );
  }
  return output;
}

function blendImageDataRegionOver(
  target: ImageData,
  source: ImageData,
  opacity: number,
  sourceLeft: number,
  sourceTop: number,
  targetBounds: EditorSelection,
) {
  for (let y = 0; y < target.height; y += 1) {
    const sourceY = targetBounds.y + y - sourceTop;
    if (sourceY < 0 || sourceY >= source.height) continue;
    for (let x = 0; x < target.width; x += 1) {
      const sourceX = targetBounds.x + x - sourceLeft;
      if (sourceX < 0 || sourceX >= source.width) continue;
      const sourceIndex = (sourceY * source.width + sourceX) * 4;
      const targetIndex = (y * target.width + x) * 4;
      const sourceAlpha = (source.data[sourceIndex + 3] / 255) * opacity;
      if (sourceAlpha <= 0) continue;
      const targetAlpha = target.data[targetIndex + 3] / 255;
      const nextAlpha = sourceAlpha + targetAlpha * (1 - sourceAlpha);
      target.data[targetIndex] = Math.round((source.data[sourceIndex] * sourceAlpha + target.data[targetIndex] * targetAlpha * (1 - sourceAlpha)) / nextAlpha);
      target.data[targetIndex + 1] = Math.round((source.data[sourceIndex + 1] * sourceAlpha + target.data[targetIndex + 1] * targetAlpha * (1 - sourceAlpha)) / nextAlpha);
      target.data[targetIndex + 2] = Math.round((source.data[sourceIndex + 2] * sourceAlpha + target.data[targetIndex + 2] * targetAlpha * (1 - sourceAlpha)) / nextAlpha);
      target.data[targetIndex + 3] = Math.round(nextAlpha * 255);
    }
  }
}

export function compositeEditorLayers(width: number, height: number, layers: EditorLayer[]) {
  const output = new ImageData(width, height);
  for (const layer of layers) {
    if (!layer.visible || layer.opacity <= 0) continue;
    blendImageDataOver(output, layer.imageData, layer.opacity / 100, 0, 0);
  }
  return output;
}

export function blendImageDataOver(target: ImageData, source: ImageData, opacity: number, left: number, top: number) {
  // 这里使用标准 source-over alpha 合成，而不是直接覆盖像素。
  // 游戏素材大量依赖半透明边缘，直接覆盖会让图层透明度和毛边预览不可信。
  for (let y = 0; y < source.height; y += 1) {
    const targetY = top + y;
    if (targetY < 0 || targetY >= target.height) continue;
    for (let x = 0; x < source.width; x += 1) {
      const targetX = left + x;
      if (targetX < 0 || targetX >= target.width) continue;
      const sourceIndex = (y * source.width + x) * 4;
      const targetIndex = (targetY * target.width + targetX) * 4;
      const sourceAlpha = (source.data[sourceIndex + 3] / 255) * opacity;
      if (sourceAlpha <= 0) continue;
      const targetAlpha = target.data[targetIndex + 3] / 255;
      const nextAlpha = sourceAlpha + targetAlpha * (1 - sourceAlpha);
      target.data[targetIndex] = Math.round((source.data[sourceIndex] * sourceAlpha + target.data[targetIndex] * targetAlpha * (1 - sourceAlpha)) / nextAlpha);
      target.data[targetIndex + 1] = Math.round((source.data[sourceIndex + 1] * sourceAlpha + target.data[targetIndex + 1] * targetAlpha * (1 - sourceAlpha)) / nextAlpha);
      target.data[targetIndex + 2] = Math.round((source.data[sourceIndex + 2] * sourceAlpha + target.data[targetIndex + 2] * targetAlpha * (1 - sourceAlpha)) / nextAlpha);
      target.data[targetIndex + 3] = Math.round(nextAlpha * 255);
    }
  }
}

export function pasteImageDataPatch(target: ImageData, patch: ImageData, left: number, top: number) {
  for (let y = 0; y < patch.height; y += 1) {
    const sourceStart = y * patch.width * 4;
    const targetStart = ((top + y) * target.width + left) * 4;
    target.data.set(patch.data.subarray(sourceStart, sourceStart + patch.width * 4), targetStart);
  }
}

export function pasteImageDataWithAlpha(target: ImageData, patch: ImageData, left: number, top: number) {
  blendImageDataOver(target, patch, 1, left, top);
}

export function imageDataFromArray(source: Uint8ClampedArray, sourceWidth: number, bounds: EditorSelection) {
  const data = new Uint8ClampedArray(bounds.width * bounds.height * 4);
  for (let y = 0; y < bounds.height; y += 1) {
    const sourceIndex = ((bounds.y + y) * sourceWidth + bounds.x) * 4;
    const targetIndex = y * bounds.width * 4;
    data.set(source.subarray(sourceIndex, sourceIndex + bounds.width * 4), targetIndex);
  }
  return new ImageData(data, bounds.width, bounds.height);
}

export function cropImageData(imageData: ImageData, selection: EditorSelection) {
  const bounds = normalizeEditorBounds(selection.x, selection.y, selection.x + selection.width, selection.y + selection.height, imageData.width, imageData.height);
  if (!bounds) return cloneImageData(imageData);
  return imageDataFromArray(imageData.data, imageData.width, bounds);
}

export function clearSelectionPixels(imageData: ImageData, selection: EditorSelectionMask) {
  for (let y = selection.bounds.y; y < selection.bounds.y + selection.bounds.height; y += 1) {
    for (let x = selection.bounds.x; x < selection.bounds.x + selection.bounds.width; x += 1) {
      if (!isEditorSelectionPixelSelected(selection, x, y, imageData.width)) continue;
      imageData.data[(y * imageData.width + x) * 4 + 3] = 0;
    }
  }
}

export function readAlphaBounds(imageData: ImageData): EditorSelection | null {
  let minX = imageData.width;
  let minY = imageData.height;
  let maxX = -1;
  let maxY = -1;
  for (let y = 0; y < imageData.height; y += 1) {
    for (let x = 0; x < imageData.width; x += 1) {
      if (imageData.data[(y * imageData.width + x) * 4 + 3] === 0) continue;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
    }
  }
  if (maxX < minX || maxY < minY) return null;
  return { x: minX, y: minY, width: maxX - minX + 1, height: maxY - minY + 1 };
}

export function addImageDataPadding(imageData: ImageData, padding: number) {
  const safePadding = Math.max(0, Math.round(padding));
  const next = new ImageData(imageData.width + safePadding * 2, imageData.height + safePadding * 2);
  pasteImageDataPatch(next, imageData, safePadding, safePadding);
  return next;
}

export function flipImageData(imageData: ImageData, direction: "horizontal" | "vertical") {
  const next = new ImageData(imageData.width, imageData.height);
  for (let y = 0; y < imageData.height; y += 1) {
    for (let x = 0; x < imageData.width; x += 1) {
      const targetX = direction === "horizontal" ? imageData.width - 1 - x : x;
      const targetY = direction === "vertical" ? imageData.height - 1 - y : y;
      const sourceIndex = (y * imageData.width + x) * 4;
      const targetIndex = (targetY * imageData.width + targetX) * 4;
      next.data[targetIndex] = imageData.data[sourceIndex];
      next.data[targetIndex + 1] = imageData.data[sourceIndex + 1];
      next.data[targetIndex + 2] = imageData.data[sourceIndex + 2];
      next.data[targetIndex + 3] = imageData.data[sourceIndex + 3];
    }
  }
  return next;
}

export function rotateImageDataClockwise(imageData: ImageData) {
  const next = new ImageData(imageData.height, imageData.width);
  for (let y = 0; y < imageData.height; y += 1) {
    for (let x = 0; x < imageData.width; x += 1) {
      const targetX = imageData.height - 1 - y;
      const targetY = x;
      const sourceIndex = (y * imageData.width + x) * 4;
      const targetIndex = (targetY * next.width + targetX) * 4;
      next.data[targetIndex] = imageData.data[sourceIndex];
      next.data[targetIndex + 1] = imageData.data[sourceIndex + 1];
      next.data[targetIndex + 2] = imageData.data[sourceIndex + 2];
      next.data[targetIndex + 3] = imageData.data[sourceIndex + 3];
    }
  }
  return next;
}

export function resizeOriginalForDocument(original: ImageData, width: number, height: number) {
  if (original.width === width && original.height === height) return original;
  const next = new ImageData(width, height);
  pasteImageDataPatch(next, cropImageData(original, { x: 0, y: 0, width: Math.min(width, original.width), height: Math.min(height, original.height) }), 0, 0);
  return next;
}

export function readEditorPointer(event: PointerEvent | MouseEvent, canvas: HTMLCanvasElement, doc: EditorDocument): ImagePoint {
  const rect = canvas.getBoundingClientRect();
  return {
    x: clamp(((event.clientX - rect.left) / rect.width) * doc.width, 0, doc.width - 0.001),
    y: clamp(((event.clientY - rect.top) / rect.height) * doc.height, 0, doc.height - 0.001),
  };
}

export function drawEditorBrush(doc: EditorDocument, point: ImagePoint, tool: EditorTool, brush: EditorBrushSettings, stroke: EditorStrokeState): EditorSelection | null {
  const layer = getActiveEditorLayer(doc);
  if (!layer) return null;
  const radius = Math.max(0.5, brush.size / 2);
  const radiusSquared = radius * radius;
  const left = clamp(Math.floor(point.x - radius), 0, doc.width - 1);
  const top = clamp(Math.floor(point.y - radius), 0, doc.height - 1);
  const right = clamp(Math.ceil(point.x + radius), 0, doc.width - 1);
  const bottom = clamp(Math.ceil(point.y + radius), 0, doc.height - 1);
  const color = parseHexColor(brush.color);
  const opacity = clamp(brush.opacity, 1, 100) / 100;
  const hardRadius = tool === "eraser" && brush.hardEraser ? radius : radius * (clamp(brush.hardness, 1, 100) / 100);
  const hardRadiusSquared = hardRadius * hardRadius;

  for (let y = top; y <= bottom; y += 1) {
    for (let x = left; x <= right; x += 1) {
      const dx = x + 0.5 - point.x;
      const dy = y + 0.5 - point.y;
      const distanceSquared = dx * dx + dy * dy;
      if (distanceSquared > radiusSquared) continue;
      if (doc.selection && !isEditorSelectionPixelSelected(doc.selection, x, y, doc.width)) continue;
      const falloff = distanceSquared <= hardRadiusSquared ? 1 : (radius - Math.sqrt(distanceSquared)) / Math.max(0.001, radius - hardRadius);
      const amount = clamp(falloff * opacity, 0, 1);
      const index = (y * doc.width + x) * 4;
      recordEditorPixelBefore(stroke.recorder, layer.imageData.data, index);
      if (tool === "eraser") {
        layer.imageData.data[index + 3] = Math.round(layer.imageData.data[index + 3] * (1 - amount));
        continue;
      }
      if (tool === "restore") {
        blendPixel(layer.imageData.data, index, doc.originalImageData.data[index], doc.originalImageData.data[index + 1], doc.originalImageData.data[index + 2], doc.originalImageData.data[index + 3], amount);
        continue;
      }
      blendPixel(layer.imageData.data, index, color.r, color.g, color.b, 255, amount);
    }
  }
  return { x: left, y: top, width: right - left + 1, height: bottom - top + 1 };
}

export function blendPixel(data: Uint8ClampedArray, index: number, red: number, green: number, blue: number, alpha: number, amount: number) {
  data[index] = Math.round(data[index] * (1 - amount) + red * amount);
  data[index + 1] = Math.round(data[index + 1] * (1 - amount) + green * amount);
  data[index + 2] = Math.round(data[index + 2] * (1 - amount) + blue * amount);
  data[index + 3] = Math.round(data[index + 3] * (1 - amount) + alpha * amount);
}

export function parseHexColor(value: string) {
  const normalized = value.replace("#", "");
  return {
    r: Number.parseInt(normalized.slice(0, 2), 16) || 0,
    g: Number.parseInt(normalized.slice(2, 4), 16) || 0,
    b: Number.parseInt(normalized.slice(4, 6), 16) || 0,
  };
}

export function readEditorDocumentColor(doc: EditorDocument, point: ImagePoint) {
  const pixel = readEditorDocumentPixel(doc, point);
  return `#${[pixel.r, pixel.g, pixel.b].map((value) => value.toString(16).padStart(2, "0")).join("")}`;
}

export function readEditorDocumentSample(doc: EditorDocument, point: ImagePoint) {
  const x = Math.floor(point.x);
  const y = Math.floor(point.y);
  const pixel = readEditorDocumentPixel(doc, point);
  return `x${x} y${y} · RGBA ${pixel.r},${pixel.g},${pixel.b},${pixel.a}`;
}

export function readEditorDocumentPixel(doc: EditorDocument, point: ImagePoint) {
  const x = Math.floor(clamp(point.x, 0, doc.width - 1));
  const y = Math.floor(clamp(point.y, 0, doc.height - 1));
  let red = 0;
  let green = 0;
  let blue = 0;
  let alpha = 0;

  const blendPixelAt = (imageData: ImageData, opacity: number, left = 0, top = 0) => {
    const sourceX = x - left;
    const sourceY = y - top;
    if (sourceX < 0 || sourceY < 0 || sourceX >= imageData.width || sourceY >= imageData.height) return;
    const index = (sourceY * imageData.width + sourceX) * 4;
    const sourceAlpha = (imageData.data[index + 3] / 255) * opacity;
    if (sourceAlpha <= 0) return;
    const targetAlpha = alpha / 255;
    const nextAlpha = sourceAlpha + targetAlpha * (1 - sourceAlpha);
    red = Math.round((imageData.data[index] * sourceAlpha + red * targetAlpha * (1 - sourceAlpha)) / nextAlpha);
    green = Math.round((imageData.data[index + 1] * sourceAlpha + green * targetAlpha * (1 - sourceAlpha)) / nextAlpha);
    blue = Math.round((imageData.data[index + 2] * sourceAlpha + blue * targetAlpha * (1 - sourceAlpha)) / nextAlpha);
    alpha = Math.round(nextAlpha * 255);
  };

  // 状态栏只需要当前指针下的一个像素。单点合成能避开整张图的 ImageData 分配，
  // 画笔移动时状态栏仍然准确，页面也不会因为取样频繁出现明显卡顿。
  for (const layer of doc.layers) {
    if (!layer.visible || layer.opacity <= 0) continue;
    blendPixelAt(layer.imageData, layer.opacity / 100);
  }
  if (doc.floatingSelection) {
    blendPixelAt(doc.floatingSelection.imageData, 1, doc.floatingSelection.bounds.x, doc.floatingSelection.bounds.y);
  }

  return { r: red, g: green, b: blue, a: alpha };
}

export function readSelectionFromDraft(draft: EditorSelectionDraft): EditorSelection {
  const x = Math.floor(Math.min(draft.start.x, draft.current.x));
  const y = Math.floor(Math.min(draft.start.y, draft.current.y));
  const right = Math.ceil(Math.max(draft.start.x, draft.current.x));
  const bottom = Math.ceil(Math.max(draft.start.y, draft.current.y));
  return { x, y, width: Math.max(1, right - x), height: Math.max(1, bottom - y) };
}

export function buildRectSelectionMask(width: number, height: number, selection: EditorSelection): EditorSelectionMask {
  const bounds = normalizeEditorBounds(selection.x, selection.y, selection.x + selection.width, selection.y + selection.height, width, height) ?? { x: 0, y: 0, width, height };
  return { kind: "rect", bounds, mask: new Uint8ClampedArray(0) };
}

export function appendLassoPoint(path: ImagePoint[], point: ImagePoint) {
  const last = path[path.length - 1];
  if (last && Math.hypot(last.x - point.x, last.y - point.y) < 1.5) return path;
  // 套索拖动会产生大量点，复制整条路径会让长路径越来越慢。
  // 这里直接追加到草稿数组，草稿只保存在 ref 里，不会破坏 React 状态不可变约定。
  path.push(point);
  return path;
}

export function buildLassoSelectionMask(width: number, height: number, path: ImagePoint[]): EditorSelectionMask | null {
  if (path.length < 3) return null;
  // 套索路径先画到离屏 canvas，再读取 alpha 作为选区 mask。
  // 这比手写多边形扫描更稳定，也能和浏览器 Canvas 的边界规则保持一致。
  const scratch = document.createElement("canvas");
  scratch.width = width;
  scratch.height = height;
  const context = scratch.getContext("2d", { willReadFrequently: true });
  if (!context) return null;
  context.beginPath();
  context.moveTo(path[0].x, path[0].y);
  for (const point of path.slice(1)) context.lineTo(point.x, point.y);
  context.closePath();
  context.fillStyle = "#fff";
  context.fill();
  const alpha = context.getImageData(0, 0, width, height).data;
  const mask = new Uint8ClampedArray(width * height);
  let minX = width;
  let minY = height;
  let maxX = -1;
  let maxY = -1;
  for (let index = 0; index < mask.length; index += 1) {
    if (alpha[index * 4 + 3] === 0) continue;
    const x = index % width;
    const y = Math.floor(index / width);
    mask[index] = 1;
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  }
  if (maxX < minX || maxY < minY) return null;
  return { kind: "lasso", bounds: { x: minX, y: minY, width: maxX - minX + 1, height: maxY - minY + 1 }, mask, path };
}

export function buildMagicWandSelection(imageData: ImageData, point: ImagePoint, tolerance: number, alphaTolerance: number, contiguous: boolean): EditorSelectionMask | null {
  const startX = Math.floor(point.x);
  const startY = Math.floor(point.y);
  const startIndex = (startY * imageData.width + startX) * 4;
  const target = [imageData.data[startIndex], imageData.data[startIndex + 1], imageData.data[startIndex + 2], imageData.data[startIndex + 3]];
  const mask = new Uint8ClampedArray(imageData.width * imageData.height);
  let minX = imageData.width;
  let minY = imageData.height;
  let maxX = -1;
  let maxY = -1;
  const accept = (x: number, y: number) => {
    const index = (y * imageData.width + x) * 4;
    return (
      Math.abs(imageData.data[index] - target[0]) <= tolerance &&
      Math.abs(imageData.data[index + 1] - target[1]) <= tolerance &&
      Math.abs(imageData.data[index + 2] - target[2]) <= tolerance &&
      Math.abs(imageData.data[index + 3] - target[3]) <= alphaTolerance
    );
  };
  const mark = (x: number, y: number) => {
    mask[y * imageData.width + x] = 1;
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  };

  if (contiguous) {
    // 连续模式只扩展相邻像素，适合点选透明背景或单个色块。
    // 非连续模式会扫描整张图，适合一次选中相同颜色的多个零散区域。
    const visited = new Uint8Array(imageData.width * imageData.height);
    const queue = [startY * imageData.width + startX];
    visited[queue[0]] = 1;

    for (let head = 0; head < queue.length; head += 1) {
      const pixelIndex = queue[head];
      const x = pixelIndex % imageData.width;
      const y = Math.floor(pixelIndex / imageData.width);
      if (!accept(x, y)) continue;
      mark(x, y);

      // 魔棒经常会点到大面积透明背景，不能用 shift() 反复移动数组。
      // 入队时就标记 visited，可以避免边界像素被多个邻居重复塞进队列。
      if (x > 0 && !visited[pixelIndex - 1]) {
        visited[pixelIndex - 1] = 1;
        queue.push(pixelIndex - 1);
      }
      if (x < imageData.width - 1 && !visited[pixelIndex + 1]) {
        visited[pixelIndex + 1] = 1;
        queue.push(pixelIndex + 1);
      }
      if (y > 0 && !visited[pixelIndex - imageData.width]) {
        visited[pixelIndex - imageData.width] = 1;
        queue.push(pixelIndex - imageData.width);
      }
      if (y < imageData.height - 1 && !visited[pixelIndex + imageData.width]) {
        visited[pixelIndex + imageData.width] = 1;
        queue.push(pixelIndex + imageData.width);
      }
    }
  } else {
    for (let y = 0; y < imageData.height; y += 1) {
      for (let x = 0; x < imageData.width; x += 1) {
        if (accept(x, y)) mark(x, y);
      }
    }
  }

  if (maxX < minX || maxY < minY) return null;
  return { kind: "magic", bounds: { x: minX, y: minY, width: maxX - minX + 1, height: maxY - minY + 1 }, mask };
}

export function normalizeEditorBounds(minX: number, minY: number, maxX: number, maxY: number, width: number, height: number): EditorSelection | null {
  const x = Math.round(clamp(Math.min(minX, maxX), 0, width));
  const y = Math.round(clamp(Math.min(minY, maxY), 0, height));
  const right = Math.round(clamp(Math.max(minX, maxX), 0, width));
  const bottom = Math.round(clamp(Math.max(minY, maxY), 0, height));
  if (right <= x || bottom <= y) return null;
  return { x, y, width: right - x, height: bottom - y };
}

export function extractSelectionClipboard(doc: EditorDocument, cut: boolean): EditorClipboardItem | null {
  const layer = getActiveEditorLayer(doc);
  if (!layer || !doc.selection) return null;
  // 复制/剪切只读取当前激活图层，避免用户在上层修边时误把所有图层扁平内容都切走。
  // 这和常见位图编辑器的图层编辑习惯一致。
  const bounds = doc.selection.bounds;
  const item = new ImageData(bounds.width, bounds.height);
  for (let y = 0; y < bounds.height; y += 1) {
    for (let x = 0; x < bounds.width; x += 1) {
      const sourceX = bounds.x + x;
      const sourceY = bounds.y + y;
      const sourcePixel = sourceY * doc.width + sourceX;
      if (!isEditorSelectionPixelSelected(doc.selection, sourceX, sourceY, doc.width)) continue;
      const sourceIndex = sourcePixel * 4;
      const targetIndex = (y * bounds.width + x) * 4;
      item.data[targetIndex] = layer.imageData.data[sourceIndex];
      item.data[targetIndex + 1] = layer.imageData.data[sourceIndex + 1];
      item.data[targetIndex + 2] = layer.imageData.data[sourceIndex + 2];
      item.data[targetIndex + 3] = layer.imageData.data[sourceIndex + 3];
      if (cut) layer.imageData.data[sourceIndex + 3] = 0;
    }
  }
  return { name: "选区", imageData: item, bounds: { ...bounds } };
}

export function isEditorSelectionPixelSelected(selection: EditorSelectionMask, x: number, y: number, width: number) {
  if (x < selection.bounds.x || y < selection.bounds.y || x >= selection.bounds.x + selection.bounds.width || y >= selection.bounds.y + selection.bounds.height) return false;
  if (selection.kind === "rect") return true;
  return selection.mask[y * width + x] > 0;
}

export function pasteFloatingSelection(doc: EditorDocument) {
  const layer = getActiveEditorLayer(doc);
  if (!layer || !doc.floatingSelection) return;
  pasteImageDataWithAlpha(layer.imageData, doc.floatingSelection.imageData, doc.floatingSelection.bounds.x, doc.floatingSelection.bounds.y);
  doc.floatingSelection = null;
  doc.selection = null;
}

export function centerClipboardBounds(bounds: EditorSelection, width: number, height: number): EditorSelection {
  return {
    ...bounds,
    x: Math.round((width - bounds.width) / 2),
    y: Math.round((height - bounds.height) / 2),
  };
}

export async function writeClipboardImage(imageData: ImageData) {
  if (!navigator.clipboard || typeof ClipboardItem === "undefined") throw new Error("当前浏览器不支持图片剪贴板写入。");
  const blob = await imageDataToPngBlob(imageData);
  await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
}

export async function readClipboardImage(): Promise<EditorClipboardItem | null> {
  // 系统剪贴板在浏览器里依赖权限和 HTTPS/本地环境，不能作为唯一数据通道。
  // 调用方始终会先使用内部剪贴板，这里只做可用时增强。
  if (!navigator.clipboard || !("read" in navigator.clipboard)) return null;
  const items = await navigator.clipboard.read();
  for (const item of items) {
    const type = item.types.find((mime) => mime.startsWith("image/"));
    if (!type) continue;
    const blob = await item.getType(type);
    const imageData = await blobToImageData(blob);
    return { name: "剪贴板", imageData, bounds: { x: 0, y: 0, width: imageData.width, height: imageData.height } };
  }
  return null;
}

export function imageDataToPngBlob(imageData: ImageData) {
  const canvas = document.createElement("canvas");
  canvas.width = imageData.width;
  canvas.height = imageData.height;
  const context = canvas.getContext("2d");
  if (!context) return Promise.reject(new Error("浏览器不支持 Canvas 导出。"));
  context.putImageData(imageData, 0, 0);
  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("PNG 生成失败。"))), "image/png");
  });
}

export function flattenImageDataOnBackground(imageData: ImageData, backgroundColor: string) {
  const color = parseHexColor(backgroundColor);
  const output = new ImageData(imageData.width, imageData.height);
  for (let index = 0; index < imageData.data.length; index += 4) {
    const alpha = imageData.data[index + 3] / 255;
    // 纯色背景导出必须变成真实不透明像素。
    // 只改变预览底色会让用户以为已经有背景，但导入其他软件后仍然透底。
    output.data[index] = Math.round(imageData.data[index] * alpha + color.r * (1 - alpha));
    output.data[index + 1] = Math.round(imageData.data[index + 1] * alpha + color.g * (1 - alpha));
    output.data[index + 2] = Math.round(imageData.data[index + 2] * alpha + color.b * (1 - alpha));
    output.data[index + 3] = 255;
  }
  return output;
}

export function blobToImageData(blob: Blob) {
  return new Promise<ImageData>((resolve, reject) => {
    const image = new Image();
    const url = URL.createObjectURL(blob);
    image.onload = () => {
      URL.revokeObjectURL(url);
      const canvas = document.createElement("canvas");
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      const context = canvas.getContext("2d", { willReadFrequently: true });
      if (!context) {
        reject(new Error("浏览器不支持 Canvas 解码。"));
        return;
      }
      context.drawImage(image, 0, 0);
      resolve(context.getImageData(0, 0, canvas.width, canvas.height));
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("剪贴板图片无法解码。"));
    };
    image.src = url;
  });
}

export function applyAlphaThreshold(imageData: ImageData, threshold: number) {
  for (let index = 3; index < imageData.data.length; index += 4) {
    imageData.data[index] = imageData.data[index] >= threshold ? 255 : 0;
  }
}

export function removeAlphaNoise(imageData: ImageData) {
  const alpha = copyAlpha(imageData);
  for (let y = 1; y < imageData.height - 1; y += 1) {
    for (let x = 1; x < imageData.width - 1; x += 1) {
      const alphaIndex = y * imageData.width + x;
      if (alpha[alphaIndex] === 0) continue;
      let neighbors = 0;
      for (let dy = -1; dy <= 1; dy += 1) {
        for (let dx = -1; dx <= 1; dx += 1) {
          if (dx === 0 && dy === 0) continue;
          if (alpha[(y + dy) * imageData.width + x + dx] > 0) neighbors += 1;
        }
      }
      if (neighbors <= 1) {
        imageData.data[alphaIndex * 4 + 3] = 0;
      }
    }
  }
}

export function morphAlpha(imageData: ImageData, amount: number) {
  const iterations = Math.max(1, Math.abs(Math.round(amount)));
  for (let iteration = 0; iteration < iterations; iteration += 1) {
    const alpha = copyAlpha(imageData);
    for (let y = 0; y < imageData.height; y += 1) {
      for (let x = 0; x < imageData.width; x += 1) {
        const alphaIndex = y * imageData.width + x;
        const nextAlpha = amount > 0 ? readMaxNeighborAlpha(alpha, imageData.width, imageData.height, x, y) : readMinNeighborAlpha(alpha, imageData.width, imageData.height, x, y);
        imageData.data[alphaIndex * 4 + 3] = nextAlpha;
      }
    }
  }
}

export function featherAlpha(imageData: ImageData, radius: number) {
  const safeRadius = Math.max(1, Math.round(radius));
  const alpha = copyAlpha(imageData);
  for (let y = 0; y < imageData.height; y += 1) {
    for (let x = 0; x < imageData.width; x += 1) {
      let total = 0;
      let count = 0;
      for (let dy = -safeRadius; dy <= safeRadius; dy += 1) {
        for (let dx = -safeRadius; dx <= safeRadius; dx += 1) {
          const sampleX = x + dx;
          const sampleY = y + dy;
          if (sampleX < 0 || sampleY < 0 || sampleX >= imageData.width || sampleY >= imageData.height) continue;
          total += alpha[sampleY * imageData.width + sampleX];
          count += 1;
        }
      }
      imageData.data[(y * imageData.width + x) * 4 + 3] = Math.round(total / Math.max(1, count));
    }
  }
}

export function copyAlpha(imageData: ImageData) {
  const alpha = new Uint8ClampedArray(imageData.width * imageData.height);
  for (let index = 0; index < alpha.length; index += 1) {
    alpha[index] = imageData.data[index * 4 + 3];
  }
  return alpha;
}

export function readMaxNeighborAlpha(alpha: Uint8ClampedArray, width: number, height: number, x: number, y: number) {
  let value = alpha[y * width + x];
  for (let dy = -1; dy <= 1; dy += 1) {
    for (let dx = -1; dx <= 1; dx += 1) {
      const sampleX = x + dx;
      const sampleY = y + dy;
      if (sampleX < 0 || sampleY < 0 || sampleX >= width || sampleY >= height) continue;
      value = Math.max(value, alpha[sampleY * width + sampleX]);
    }
  }
  return value;
}

export function readMinNeighborAlpha(alpha: Uint8ClampedArray, width: number, height: number, x: number, y: number) {
  let value = alpha[y * width + x];
  for (let dy = -1; dy <= 1; dy += 1) {
    for (let dx = -1; dx <= 1; dx += 1) {
      const sampleX = x + dx;
      const sampleY = y + dy;
      if (sampleX < 0 || sampleY < 0 || sampleX >= width || sampleY >= height) {
        value = 0;
        continue;
      }
      value = Math.min(value, alpha[sampleY * width + sampleX]);
    }
  }
  return value;
}

export function exportEditorPng(doc: EditorDocument | null, options?: EditorExportOptions) {
  if (!doc) return Promise.reject(new Error("当前没有可导出的编辑图。"));
  const imageData = compositeEditorDocument(doc);
  return imageDataToPngBlob(options?.backgroundMode === "color" ? flattenImageDataOnBackground(imageData, options.backgroundColor) : imageData);
}

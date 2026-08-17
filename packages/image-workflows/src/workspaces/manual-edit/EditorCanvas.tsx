import React, { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import type {
  EditorBrushSettings,
  EditorClipboardItem,
  EditorDocument,
  EditorExportBackgroundMode,
  EditorHistoryEntry,
  EditorLayerHistoryState,
  EditorPixelHistoryState,
  EditorSelection,
  EditorSelectionHistoryState,
  EditorSnapshot,
  EditorTool,
  EditorZoomPreviewMode,
} from "@gameknife/editor-core";
import type { FailureDialogState, ManualEditSource } from "../../types/manualEdit";
import { isTypingTarget } from "../../utils/dom";
import { clamp } from "../../utils/math";
import { EDITOR_HISTORY_LIMIT, EDITOR_HISTORY_MEMORY_LIMIT_BYTES, EDITOR_SNAPSHOT_LIMIT } from "./constants";
import { clearManualEditorScheduledWork } from "./manualEditorScheduling";
import type { EditorLassoDraft, EditorMoveDraft, EditorSelectionDraft, EditorStatus, EditorStrokeState, ImagePoint, ManualEditorHandle } from "./types";
import {
  addImageDataPadding,
  applyEditorHistoryEntry,
  appendLassoPoint,
  applyAlphaThreshold,
  blobToImageData,
  buildLassoSelectionMask,
  buildMagicWandSelection,
  buildRectSelectionMask,
  centerClipboardBounds,
  buildEditorStrokeHistoryStates,
  captureEditorLayerHistoryState,
  captureEditorPixelHistoryState,
  captureEditorSelectionHistoryState,
  clearSelectionPixels,
  cloneEditorClipboardItem,
  cloneEditorLayer,
  cloneEditorSnapshot,
  cloneImageData,
  compositeEditorDocument,
  compositeEditorLayers,
  createBlankEditorLayer,
  createEditorId,
  createEditorPixelRecorder,
  cropImageData,
  drawEditorBrush,
  exportEditorPng,
  extractSelectionClipboard,
  expandEditorPixelHistoryState,
  estimateEditorHistoryBytes,
  featherAlpha,
  flipImageData,
  getActiveEditorLayer,
  isEditorSelectionPixelSelected,
  morphAlpha,
  normalizeEditorBounds,
  pasteFloatingSelection,
  readAlphaBounds,
  readClipboardImage,
  readEditorDocumentColor,
  readEditorPointer,
  readEditorStatus,
  readSelectionFromDraft,
  removeAlphaNoise,
  renderEditorCanvas,
  restoreEditorSnapshot,
  rotateImageDataClockwise,
  unionEditorBounds,
  writeClipboardImage,
} from "@gameknife/editor-core";

const EDITOR_STATUS_SYNC_INTERVAL_MS = 90;

type EditorSyncOptions = {
  redrawBitmap?: boolean;
  bitmapBounds?: EditorSelection;
  status?: "immediate" | "deferred" | "none";
  layout?: boolean;
};

export const EditorCanvas = forwardRef<ManualEditorHandle, {
  source: ManualEditSource;
  tool: EditorTool;
  brush: EditorBrushSettings;
  gridVisible: boolean;
  transparentBackgroundVisible: boolean;
  exportBackgroundMode: EditorExportBackgroundMode;
  exportBackgroundColor: string;
  magicTolerance: number;
  magicAlphaTolerance: number;
  magicContiguous: boolean;
  zoomPreviewMode: EditorZoomPreviewMode;
  onBrushChange: React.Dispatch<React.SetStateAction<EditorBrushSettings>>;
  onStatusChange: (status: EditorStatus) => void;
  onFailure: React.Dispatch<React.SetStateAction<FailureDialogState | null>>;
}>(function EditorCanvas({
  source,
  tool,
  brush,
  gridVisible,
  transparentBackgroundVisible,
  exportBackgroundMode,
  exportBackgroundColor,
  magicTolerance,
  magicAlphaTolerance,
  magicContiguous,
  zoomPreviewMode,
  onBrushChange,
  onStatusChange,
  onFailure,
}, ref) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const overlayRef = useRef<HTMLCanvasElement | null>(null);
  const documentRef = useRef<EditorDocument | null>(null);
  const historyRef = useRef<EditorHistoryEntry[]>([]);
  const redoRef = useRef<EditorHistoryEntry[]>([]);
  const snapshotsRef = useRef<EditorSnapshot[]>([]);
  const clipboardRef = useRef<EditorClipboardItem | null>(null);
  const strokeRef = useRef<EditorStrokeState | null>(null);
  const selectionDraftRef = useRef<EditorSelectionDraft | null>(null);
  const lassoDraftRef = useRef<EditorLassoDraft | null>(null);
  const moveDraftRef = useRef<EditorMoveDraft | null>(null);
  const layerOpacityDraftRef = useRef<{ layerId: string; before: EditorLayerHistoryState; originalOpacity: number } | null>(null);
  const pointerRef = useRef<ImagePoint | null>(null);
  const brushRef = useRef(brush);
  const toolRef = useRef(tool);
  const zoomPreviewModeRef = useRef(zoomPreviewMode);
  const onStatusChangeRef = useRef(onStatusChange);
  const renderFrameRef = useRef<number | null>(null);
  const renderNeedsBitmapRef = useRef(false);
  const renderBitmapBoundsRef = useRef<EditorSelection | null>(null);
  const statusTimerRef = useRef<number | null>(null);
  const lastStatusSyncRef = useRef(0);
  const [, setLayoutRevision] = useState(0);

  function emitStatus() {
    lastStatusSyncRef.current = performance.now();
    onStatusChangeRef.current(readEditorStatus(documentRef.current, historyRef.current, redoRef.current, snapshotsRef.current, pointerRef.current));
  }

  function scheduleStatusSync(mode: EditorSyncOptions["status"] = "deferred") {
    if (mode === "none") return;
    if (mode === "immediate") {
      if (statusTimerRef.current !== null) {
        window.clearTimeout(statusTimerRef.current);
        statusTimerRef.current = null;
      }
      emitStatus();
      return;
    }
    if (statusTimerRef.current !== null) return;
    const elapsed = performance.now() - lastStatusSyncRef.current;
    const delay = Math.max(0, EDITOR_STATUS_SYNC_INTERVAL_MS - elapsed);
    statusTimerRef.current = window.setTimeout(() => {
      statusTimerRef.current = null;
      emitStatus();
    }, delay);
  }

  function renderNow() {
    renderFrameRef.current = null;
    const redrawBitmap = renderNeedsBitmapRef.current;
    const bitmapBounds = renderBitmapBoundsRef.current ?? undefined;
    renderNeedsBitmapRef.current = false;
    renderBitmapBoundsRef.current = null;
    renderCurrentCanvas(redrawBitmap, bitmapBounds);
  }

  function renderCurrentCanvas(redrawBitmap: boolean, bitmapBounds?: EditorSelection) {
    renderEditorCanvas(
      canvasRef.current,
      overlayRef.current,
      documentRef.current,
      pointerRef.current,
      brushRef.current,
      toolRef.current,
      zoomPreviewModeRef.current,
      lassoDraftRef.current,
      redrawBitmap,
      bitmapBounds,
    );
  }

  function scheduleRender(redrawBitmap: boolean, bitmapBounds?: EditorSelection) {
    if (redrawBitmap) {
      if (!renderNeedsBitmapRef.current) {
        renderBitmapBoundsRef.current = bitmapBounds ? { ...bitmapBounds } : null;
      } else if (renderBitmapBoundsRef.current && bitmapBounds) {
        renderBitmapBoundsRef.current = unionEditorBounds(renderBitmapBoundsRef.current, bitmapBounds);
      } else {
        // 任意一次完整重绘请求都会覆盖同一帧内已经累计的局部脏区。
        renderBitmapBoundsRef.current = null;
      }
      renderNeedsBitmapRef.current = true;
    }
    if (renderFrameRef.current !== null) return;
    renderFrameRef.current = window.requestAnimationFrame(renderNow);
  }

  function sync(options: EditorSyncOptions = {}) {
    scheduleRender(options.redrawBitmap ?? true, options.bitmapBounds);
    scheduleStatusSync(options.status ?? "deferred");
    if (options.layout) {
      setLayoutRevision((current) => current + 1);
    }
  }

  useEffect(() => {
    const doc = documentRef.current;
    const canvas = canvasRef.current;
    const overlay = overlayRef.current;
    if (!doc || !canvas || !overlay) return;
    if (canvas.width === doc.width && canvas.height === doc.height && overlay.width === doc.width && overlay.height === doc.height) return;

    // 正常路径会在图片加载完成时立即渲染首帧。
    // 这里处理热更新、外层工作台延迟挂载等异常时序，避免状态栏已有图片尺寸但真实 canvas 仍是默认 300×150。
    renderCurrentCanvas(true);
  });

  useEffect(() => {
    let cancelled = false;
    const abortController = new AbortController();

    async function openSourceImage() {
      try {
        // 手动编辑入口同时支持本地上传、任务结果预览和跨标签页临时传递。
        // 已经持有 Blob 时不能再绕回 fetch(blob:url)，否则对象 URL 被释放或浏览器限制读取时会直接失败。
        // 只有外部调用没有传 Blob 时才按 URL 读取，保持这个编辑器仍然支持普通同源资源地址。
        const imageData = await blobToImageData(await readSourceBlob(source, abortController.signal));
        if (cancelled) return;

        const originalImageData = cloneImageData(imageData);
        const layerId = createEditorId("layer");
        documentRef.current = {
          name: source.name,
          width: imageData.width,
          height: imageData.height,
          layers: [{ id: layerId, name: "原图", visible: true, opacity: 100, imageData }],
          activeLayerId: layerId,
          originalImageData,
          selection: null,
          floatingSelection: null,
          dirty: false,
        };
        historyRef.current = [];
        redoRef.current = [];
        snapshotsRef.current = [];
        layerOpacityDraftRef.current = null;
        // 首次导入图片后必须马上把 ImageData 写进真实 canvas。
        // 包化后的工作台外层会同时处理缩放和居中，如果首帧只等待 rAF，
        // 页面可能先拿到文档尺寸但 canvas 仍停在浏览器默认 300×150，用户看到的就是空棋盘。
        renderCurrentCanvas(true);
        sync({ redrawBitmap: true, status: "immediate", layout: true });
      } catch (error) {
        if (cancelled || (error instanceof Error && error.name === "AbortError")) return;
        onFailure({
          title: "图片加载失败",
          message: "手动编辑器无法读取当前图片。",
          detail: error instanceof Error ? error.message : "浏览器没有成功解码图片，请重新导入。",
        });
      }
    }

    void openSourceImage();
    return () => {
      cancelled = true;
      abortController.abort();
    };
  }, [source.name, source.url]);

  useEffect(() => {
    brushRef.current = brush;
    toolRef.current = tool;
    zoomPreviewModeRef.current = zoomPreviewMode;
    scheduleRender(false);
    scheduleStatusSync("deferred");
  }, [gridVisible, brush, tool, zoomPreviewMode]);

  useEffect(() => {
    onStatusChangeRef.current = onStatusChange;
  }, [onStatusChange]);

  useEffect(() => {
    return () => {
      clearManualEditorScheduledWork(
        renderFrameRef,
        statusTimerRef,
        (frameId) => window.cancelAnimationFrame(frameId),
        (timerId) => window.clearTimeout(timerId),
      );
    };
  }, []);

  useEffect(() => {
    const setToolFromKeyboard = (event: KeyboardEvent, nextTool: EditorTool) => {
      event.preventDefault();
      const button = document.querySelector<HTMLButtonElement>(`.editor-tool-button[data-tool="${nextTool}"]`);
      button?.click();
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (isTypingTarget(event.target)) return;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") {
        event.preventDefault();
        if (event.shiftKey) {
          redo();
        } else {
          undo();
        }
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "y") {
        event.preventDefault();
        redo();
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "c") {
        event.preventDefault();
        void copySelection();
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "x") {
        event.preventDefault();
        void cutSelection();
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "v") {
        event.preventDefault();
        void pasteSelection();
        return;
      }
      const key = event.key.toLowerCase();
      if (key === "b") setToolFromKeyboard(event, "brush");
      if (key === "e") setToolFromKeyboard(event, "eraser");
      if (key === "r") setToolFromKeyboard(event, "restore");
      if (key === "i") setToolFromKeyboard(event, "picker");
      if (key === "v") setToolFromKeyboard(event, "pan");
      if (key === "m") setToolFromKeyboard(event, "move-selection");
      if (key === "c") setToolFromKeyboard(event, "rect-selection");
      if (key === "l") setToolFromKeyboard(event, "lasso-selection");
      if (key === "w") setToolFromKeyboard(event, "magic-wand");
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const pushHistoryEntry = (entry: EditorHistoryEntry) => {
    historyRef.current = trimEditorHistory([...historyRef.current, entry]);
    redoRef.current = [];
  };

  const commitHistoryEntry = (entry: EditorHistoryEntry, options: Pick<EditorSyncOptions, "status"> = {}) => {
    pushHistoryEntry(entry);
    const doc = documentRef.current;
    if (!doc) return;
    doc.dirty = true;
    sync({
      redrawBitmap: entry.redrawBitmap,
      bitmapBounds: entry.kind === "pixels" ? entry.bounds : undefined,
      status: options.status ?? "immediate",
      layout: entry.layout,
    });
  };

  const createHistoryMetadata = (title: string, redrawBitmap: boolean, layout = false) => ({
    id: createEditorId("history"),
    title,
    createdAt: Date.now(),
    redrawBitmap,
    layout,
  });

  const commitSnapshotChange = (title: string, before: EditorSnapshot, options: EditorSyncOptions = {}) => {
    const doc = documentRef.current;
    if (!doc) return;
    commitHistoryEntry({
      ...createHistoryMetadata(title, options.redrawBitmap ?? true, options.layout ?? false),
      kind: "snapshot",
      before,
      after: cloneEditorSnapshot(doc, title),
    }, options);
  };

  const commitSelectionChange = (title: string, before: EditorSelectionHistoryState, options: EditorSyncOptions = {}) => {
    const doc = documentRef.current;
    if (!doc) return;
    commitHistoryEntry({
      ...createHistoryMetadata(title, options.redrawBitmap ?? false, options.layout ?? false),
      kind: "selection",
      before,
      after: captureEditorSelectionHistoryState(doc),
    }, options);
  };

  const commitLayerChange = (title: string, before: EditorLayerHistoryState, options: EditorSyncOptions = {}) => {
    const doc = documentRef.current;
    if (!doc) return;
    commitHistoryEntry({
      ...createHistoryMetadata(title, options.redrawBitmap ?? true, options.layout ?? false),
      kind: "layers",
      before,
      after: captureEditorLayerHistoryState(doc),
    }, options);
  };

  const commitPixelChange = (
    title: string,
    layerId: string,
    bounds: EditorSelection,
    before: EditorPixelHistoryState,
    options: EditorSyncOptions = {},
  ) => {
    const doc = documentRef.current;
    const after = doc ? captureEditorPixelHistoryState(doc, layerId, bounds) : null;
    if (!doc || !after) return;
    commitHistoryEntry({
      ...createHistoryMetadata(title, options.redrawBitmap ?? true, options.layout ?? false),
      kind: "pixels",
      layerId,
      bounds,
      before,
      after,
    }, options);
  };

  const commitLayerOpacityPreview = (layerId: string) => {
    const doc = documentRef.current;
    const opacityDraft = layerOpacityDraftRef.current;
    if (!doc || !opacityDraft || opacityDraft.layerId !== layerId) return;

    layerOpacityDraftRef.current = null;
    const layer = doc.layers.find((item) => item.id === layerId);
    if (!layer || layer.opacity === opacityDraft.originalOpacity) {
      sync({ redrawBitmap: true, status: "immediate" });
      return;
    }

    commitLayerChange("调整图层透明度", opacityDraft.before);
  };

  const undo = () => {
    const doc = documentRef.current;
    const entry = historyRef.current.pop();
    if (!doc || !entry) return;
    applyEditorHistoryEntry(doc, entry, "before");
    redoRef.current.push(entry);
    doc.dirty = true;
    sync({
      redrawBitmap: entry.redrawBitmap,
      bitmapBounds: entry.kind === "pixels" ? entry.bounds : undefined,
      status: "immediate",
      layout: entry.layout,
    });
  };

  const redo = () => {
    const doc = documentRef.current;
    const entry = redoRef.current.pop();
    if (!doc || !entry) return;
    applyEditorHistoryEntry(doc, entry, "after");
    historyRef.current.push(entry);
    doc.dirty = true;
    sync({
      redrawBitmap: entry.redrawBitmap,
      bitmapBounds: entry.kind === "pixels" ? entry.bounds : undefined,
      status: "immediate",
      layout: entry.layout,
    });
  };

  const copySelection = async () => {
    const doc = documentRef.current;
    if (!doc?.selection) return;
    const item = extractSelectionClipboard(doc, false);
    if (!item) return;
    clipboardRef.current = item;
    try {
      await writeClipboardImage(item.imageData);
    } catch (error) {
      onFailure({
        title: "系统剪贴板不可用",
        message: "已复制到编辑器内部剪贴板，可以继续粘贴。",
        detail: error instanceof Error ? error.message : "浏览器没有允许写入图片剪贴板。",
      });
    }
    sync({ redrawBitmap: false, status: "immediate" });
  };

  const cutSelection = async () => {
    const doc = documentRef.current;
    if (!doc?.selection) return;
    const layer = getActiveEditorLayer(doc);
    if (!layer) return;
    const bounds = { ...doc.selection.bounds };
    const before = captureEditorPixelHistoryState(doc, layer.id, bounds);
    if (!before) return;
    const item = extractSelectionClipboard(doc, true);
    if (!item) return;
    clipboardRef.current = item;
    commitPixelChange("剪切选区", layer.id, bounds, before);
    try {
      await writeClipboardImage(item.imageData);
    } catch {
      // 系统剪贴板只是增强能力，内部剪贴板已经保存了像素块，不能因为权限失败影响主流程。
    }
  };

  const pasteSelection = async () => {
    const doc = documentRef.current;
    if (!doc) return;
    let item = clipboardRef.current ? cloneEditorClipboardItem(clipboardRef.current) : null;
    if (!item) {
      item = await readClipboardImage().catch(() => null);
      if (item) clipboardRef.current = cloneEditorClipboardItem(item);
    }
    if (!item) {
      onFailure({
        title: "没有可粘贴内容",
        message: "请先复制或剪切一个选区。",
        detail: "浏览器没有读取到图片剪贴板，编辑器内部剪贴板也为空。",
      });
      return;
    }
    const before = captureEditorSelectionHistoryState(doc);
    item.bounds = centerClipboardBounds(item.bounds, doc.width, doc.height);
    doc.floatingSelection = item;
    // 浮动选区参与最终合成，粘贴后要刷新位图，但历史只保存局部浮动内容。
    commitSelectionChange("粘贴选区", before, { redrawBitmap: true });
  };

  const commitFloatingSelection = () => {
    const doc = documentRef.current;
    if (!doc?.floatingSelection) return;
    const layer = getActiveEditorLayer(doc);
    if (!layer) return;
    const bounds = normalizeEditorBounds(
      doc.floatingSelection.bounds.x,
      doc.floatingSelection.bounds.y,
      doc.floatingSelection.bounds.x + doc.floatingSelection.bounds.width,
      doc.floatingSelection.bounds.y + doc.floatingSelection.bounds.height,
      doc.width,
      doc.height,
    );
    if (!bounds) return;
    const before = captureEditorPixelHistoryState(doc, layer.id, bounds);
    if (!before) return;
    pasteFloatingSelection(doc);
    commitPixelChange("贴入选区", layer.id, bounds, before);
  };

  useImperativeHandle(ref, () => ({
    exportPngBlob: (options) => exportEditorPng(documentRef.current, options),
    markSaved: () => {
      const doc = documentRef.current;
      if (!doc) return;
      doc.dirty = false;
      sync({ redrawBitmap: false, status: "immediate" });
    },
    undo,
    redo,
    clearSelection: () => {
      const doc = documentRef.current;
      if (!doc || (!doc.selection && !doc.floatingSelection)) return;
      const before = captureEditorSelectionHistoryState(doc);
      doc.selection = null;
      doc.floatingSelection = null;
      commitSelectionChange("清除选区", before, { redrawBitmap: Boolean(before.floatingSelection) });
    },
    deleteSelection: () => {
      const doc = documentRef.current;
      if (!doc?.selection) return;
      const layer = getActiveEditorLayer(doc);
      if (!layer) return;
      const bounds = { ...doc.selection.bounds };
      const before = captureEditorPixelHistoryState(doc, layer.id, bounds);
      if (!before) return;
      clearSelectionPixels(layer.imageData, doc.selection);
      commitPixelChange("删除选区", layer.id, bounds, before);
    },
    copySelection,
    cutSelection,
    pasteSelection,
    commitFloatingSelection,
    cropSelection: () => {
      const doc = documentRef.current;
      if (!doc?.selection) return;
      cropDocumentToSelection(doc, "裁到选区");
    },
    createLayer: () => {
      const doc = documentRef.current;
      if (!doc) return;
      const before = cloneEditorSnapshot(doc, "新建图层");
      const layer = createBlankEditorLayer(doc.width, doc.height, `图层 ${doc.layers.length + 1}`);
      doc.layers = [...doc.layers, layer];
      doc.activeLayerId = layer.id;
      commitSnapshotChange("新建图层", before);
    },
    duplicateLayer: () => {
      const doc = documentRef.current;
      const layer = doc ? getActiveEditorLayer(doc) : null;
      if (!doc || !layer) return;
      const before = cloneEditorSnapshot(doc, "复制图层");
      const index = doc.layers.findIndex((item) => item.id === layer.id);
      const duplicate = { ...cloneEditorLayer(layer), id: createEditorId("layer"), name: `${layer.name} 副本` };
      doc.layers = [...doc.layers.slice(0, index + 1), duplicate, ...doc.layers.slice(index + 1)];
      doc.activeLayerId = duplicate.id;
      commitSnapshotChange("复制图层", before);
    },
    deleteLayer: (layerId) => {
      const doc = documentRef.current;
      if (!doc || doc.layers.length <= 1) return;
      const before = cloneEditorSnapshot(doc, "删除图层");
      const index = doc.layers.findIndex((layer) => layer.id === layerId);
      doc.layers = doc.layers.filter((layer) => layer.id !== layerId);
      if (doc.activeLayerId === layerId) {
        doc.activeLayerId = doc.layers[Math.max(0, index - 1)]?.id ?? doc.layers[0].id;
      }
      commitSnapshotChange("删除图层", before);
    },
    setActiveLayer: (layerId) => {
      const doc = documentRef.current;
      if (!doc || !doc.layers.some((layer) => layer.id === layerId)) return;
      doc.activeLayerId = layerId;
      sync({ redrawBitmap: false, status: "immediate" });
    },
    updateLayerName: (layerId, name) => {
      const doc = documentRef.current;
      const layer = doc?.layers.find((item) => item.id === layerId);
      if (!doc || !layer) return;
      if (layer.name === (name || "图层")) return;
      const before = captureEditorLayerHistoryState(doc);
      layer.name = name || "图层";
      doc.activeLayerId = layerId;
      commitLayerChange("重命名图层", before, { redrawBitmap: false });
    },
    updateLayerOpacity: (layerId, opacity) => {
      const doc = documentRef.current;
      const layer = doc?.layers.find((item) => item.id === layerId);
      if (!doc || !layer) return;
      layerOpacityDraftRef.current = null;
      const nextOpacity = clamp(Math.round(opacity), 0, 100);
      if (layer.opacity === nextOpacity) return;
      const before = captureEditorLayerHistoryState(doc);
      layer.opacity = nextOpacity;
      doc.activeLayerId = layerId;
      commitLayerChange("调整图层透明度", before);
    },
    previewLayerOpacity: (layerId, opacity) => {
      const doc = documentRef.current;
      const layer = doc?.layers.find((item) => item.id === layerId);
      if (!doc || !layer) return;
      if (layerOpacityDraftRef.current && layerOpacityDraftRef.current.layerId !== layerId) {
        commitLayerOpacityPreview(layerOpacityDraftRef.current.layerId);
      }
      if (!layerOpacityDraftRef.current) {
        // 拖动透明度滑杆时要即时预览，但历史记录只能落一次。
        // 这里只保存图层展示属性，避免每次拖动开始时复制大图像素。
        layerOpacityDraftRef.current = {
          layerId,
          before: captureEditorLayerHistoryState(doc),
          originalOpacity: layer.opacity,
        };
      }
      layer.opacity = clamp(Math.round(opacity), 0, 100);
      doc.activeLayerId = layerId;
      sync({ redrawBitmap: true, status: "deferred" });
    },
    commitLayerOpacity: commitLayerOpacityPreview,
    toggleLayerVisibility: (layerId) => {
      const doc = documentRef.current;
      const layer = doc?.layers.find((item) => item.id === layerId);
      if (!doc || !layer) return;
      const before = captureEditorLayerHistoryState(doc);
      layer.visible = !layer.visible;
      doc.activeLayerId = layerId;
      commitLayerChange("切换图层显示", before);
    },
    moveLayer: (layerId, direction) => {
      const doc = documentRef.current;
      if (!doc) return;
      const index = doc.layers.findIndex((layer) => layer.id === layerId);
      const nextIndex = direction === "up" ? index + 1 : index - 1;
      if (index < 0 || nextIndex < 0 || nextIndex >= doc.layers.length) return;
      const before = captureEditorLayerHistoryState(doc);
      const layers = [...doc.layers];
      [layers[index], layers[nextIndex]] = [layers[nextIndex], layers[index]];
      doc.layers = layers;
      doc.activeLayerId = layerId;
      commitLayerChange("移动图层", before);
    },
    mergeLayerDown: (layerId) => {
      const doc = documentRef.current;
      if (!doc) return;
      const index = doc.layers.findIndex((layer) => layer.id === layerId);
      if (index <= 0) return;
      const before = cloneEditorSnapshot(doc, "向下合并");
      const lower = doc.layers[index - 1];
      const upper = doc.layers[index];
      lower.imageData = compositeEditorLayers(doc.width, doc.height, [lower, upper]);
      lower.opacity = 100;
      lower.visible = true;
      lower.name = `${lower.name}+${upper.name}`;
      doc.layers = doc.layers.filter((layer) => layer.id !== upper.id);
      doc.activeLayerId = lower.id;
      commitSnapshotChange("向下合并", before);
    },
    flattenLayers: () => {
      const doc = documentRef.current;
      if (!doc) return;
      const before = cloneEditorSnapshot(doc, "扁平化");
      const merged = compositeEditorDocument(doc);
      const layerId = createEditorId("layer");
      doc.layers = [{ id: layerId, name: "合并图层", visible: true, opacity: 100, imageData: merged }];
      doc.activeLayerId = layerId;
      doc.selection = null;
      doc.floatingSelection = null;
      commitSnapshotChange("扁平化", before);
    },
    jumpToHistory: (index) => {
      const doc = documentRef.current;
      if (!doc || index < 0 || index >= historyRef.current.length) return;
      // 历史节点可能是局部像素或属性状态，按倒序逐条恢复才能保持各记录类型独立。
      for (let cursor = historyRef.current.length - 1; cursor > index; cursor -= 1) {
        applyEditorHistoryEntry(doc, historyRef.current[cursor], "before");
      }
      historyRef.current = historyRef.current.slice(0, index + 1);
      redoRef.current = [];
      doc.dirty = true;
      sync({ redrawBitmap: true, status: "immediate", layout: true });
    },
    createSnapshot: () => {
      const doc = documentRef.current;
      if (!doc) return;
      snapshotsRef.current = [...snapshotsRef.current.slice(-(EDITOR_SNAPSHOT_LIMIT - 1)), cloneEditorSnapshot(doc, `快照 ${snapshotsRef.current.length + 1}`)];
      sync({ redrawBitmap: false, status: "immediate" });
    },
    restoreSnapshot: (snapshotId) => {
      const doc = documentRef.current;
      const snapshot = snapshotsRef.current.find((item) => item.id === snapshotId);
      if (!doc || !snapshot) return;
      const before = cloneEditorSnapshot(doc, "恢复快照");
      restoreEditorSnapshot(doc, snapshot);
      commitSnapshotChange("恢复快照", before, { layout: before.width !== snapshot.width || before.height !== snapshot.height });
    },
    trimTransparent: () => {
      const doc = documentRef.current;
      if (!doc) return;
      const bbox = readAlphaBounds(compositeEditorDocument(doc));
      if (!bbox) return;
      cropDocumentToBounds(doc, bbox, "裁透明边");
    },
    addPadding: (padding) => {
      const doc = documentRef.current;
      if (!doc) return;
      const before = cloneEditorSnapshot(doc, "加留边");
      doc.layers = doc.layers.map((layer) => ({ ...layer, imageData: addImageDataPadding(layer.imageData, padding) }));
      doc.width += Math.max(0, Math.round(padding)) * 2;
      doc.height += Math.max(0, Math.round(padding)) * 2;
      doc.originalImageData = addImageDataPadding(doc.originalImageData, padding);
      doc.selection = null;
      commitSnapshotChange("加留边", before, { layout: true });
    },
    flipHorizontal: () => {
      const doc = documentRef.current;
      if (!doc) return;
      const before = cloneEditorSnapshot(doc, "水平翻转");
      doc.layers = doc.layers.map((layer) => ({ ...layer, imageData: flipImageData(layer.imageData, "horizontal") }));
      doc.originalImageData = flipImageData(doc.originalImageData, "horizontal");
      doc.selection = null;
      commitSnapshotChange("水平翻转", before);
    },
    flipVertical: () => {
      const doc = documentRef.current;
      if (!doc) return;
      const before = cloneEditorSnapshot(doc, "垂直翻转");
      doc.layers = doc.layers.map((layer) => ({ ...layer, imageData: flipImageData(layer.imageData, "vertical") }));
      doc.originalImageData = flipImageData(doc.originalImageData, "vertical");
      doc.selection = null;
      commitSnapshotChange("垂直翻转", before);
    },
    rotateClockwise: () => {
      const doc = documentRef.current;
      if (!doc) return;
      const before = cloneEditorSnapshot(doc, "旋转90");
      doc.layers = doc.layers.map((layer) => ({ ...layer, imageData: rotateImageDataClockwise(layer.imageData) }));
      doc.originalImageData = rotateImageDataClockwise(doc.originalImageData);
      doc.width = doc.layers[0].imageData.width;
      doc.height = doc.layers[0].imageData.height;
      doc.selection = null;
      commitSnapshotChange("旋转90", before, { layout: true });
    },
    applyAlphaThreshold: (threshold) => applyAlphaOperation((data) => applyAlphaThreshold(data, threshold)),
    removeAlphaNoise: () => applyAlphaOperation(removeAlphaNoise),
    contractAlpha: (amount) => applyAlphaOperation((data) => morphAlpha(data, -amount)),
    expandAlpha: (amount) => applyAlphaOperation((data) => morphAlpha(data, amount)),
    featherAlpha: (radius) => applyAlphaOperation((data) => featherAlpha(data, radius)),
  }));

  function applyAlphaOperation(operation: (imageData: ImageData) => void) {
    const doc = documentRef.current;
    const layer = doc ? getActiveEditorLayer(doc) : null;
    if (!doc || !layer) return;
    const bounds = { x: 0, y: 0, width: doc.width, height: doc.height };
    const before = captureEditorPixelHistoryState(doc, layer.id, bounds);
    if (!before) return;
    operation(layer.imageData);
    commitPixelChange("修边", layer.id, bounds, before);
  }

  function cropDocumentToSelection(doc: EditorDocument, title: string) {
    if (!doc.selection) return;
    cropDocumentToBounds(doc, doc.selection.bounds, title);
  }

  function cropDocumentToBounds(doc: EditorDocument, bounds: EditorSelection, title: string) {
    const before = cloneEditorSnapshot(doc, title);
    doc.layers = doc.layers.map((layer) => ({ ...layer, imageData: cropImageData(layer.imageData, bounds) }));
    doc.originalImageData = cropImageData(doc.originalImageData, bounds);
    doc.width = bounds.width;
    doc.height = bounds.height;
    doc.selection = null;
    doc.floatingSelection = null;
    commitSnapshotChange(title, before, { layout: true });
  }

  const startPointerEdit = (event: React.PointerEvent<HTMLDivElement>) => {
    const doc = documentRef.current;
    const canvas = canvasRef.current;
    if (!doc || !canvas || tool === "pan") return;
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    const point = readEditorPointer(event.nativeEvent, canvas, doc);
    pointerRef.current = point;
    if (tool === "picker") {
      const color = readEditorDocumentColor(doc, point);
      onBrushChange((current) => ({ ...current, color }));
      sync({ redrawBitmap: false, status: "immediate" });
      return;
    }
    if (tool === "magic-wand") {
      const before = captureEditorSelectionHistoryState(doc);
      doc.selection = buildMagicWandSelection(compositeEditorDocument(doc), point, magicTolerance, magicAlphaTolerance, magicContiguous);
      commitSelectionChange("魔棒选区", before, { redrawBitmap: false });
      return;
    }
    if (tool === "rect-selection") {
      selectionDraftRef.current = { start: point, current: point, before: captureEditorSelectionHistoryState(doc) };
      doc.selection = buildRectSelectionMask(doc.width, doc.height, readSelectionFromDraft(selectionDraftRef.current));
      sync({ redrawBitmap: false, status: "deferred" });
      return;
    }
    if (tool === "lasso-selection") {
      lassoDraftRef.current = { pointerId: event.pointerId, before: captureEditorSelectionHistoryState(doc), path: [point] };
      doc.selection = null;
      sync({ redrawBitmap: false, status: "deferred" });
      return;
    }
    if (tool === "move-selection") {
      const layer = getActiveEditorLayer(doc);
      if (!layer) return;
      if (!doc.floatingSelection && doc.selection) {
        if (!isEditorSelectionPixelSelected(doc.selection, Math.floor(point.x), Math.floor(point.y), doc.width)) return;
      }
      const initialBounds = doc.floatingSelection?.bounds ?? doc.selection?.bounds;
      if (!initialBounds) return;
      const historyBounds = normalizeEditorBounds(
        initialBounds.x,
        initialBounds.y,
        initialBounds.x + initialBounds.width,
        initialBounds.y + initialBounds.height,
        doc.width,
        doc.height,
      );
      if (!historyBounds) return;
      const before = captureEditorPixelHistoryState(doc, layer.id, historyBounds);
      if (!before) return;
      if (doc.selection) doc.floatingSelection = extractSelectionClipboard(doc, true);
      if (!doc.floatingSelection) return;
      moveDraftRef.current = {
        pointerId: event.pointerId,
        layerId: layer.id,
        before,
        start: point,
        initialBounds: { ...initialBounds },
        historyBounds,
      };
      doc.selection = null;
      sync({ redrawBitmap: true, bitmapBounds: historyBounds, status: "deferred" });
      return;
    }
    const layer = getActiveEditorLayer(doc);
    if (!layer || !["brush", "eraser", "restore"].includes(tool)) return;
    strokeRef.current = {
      pointerId: event.pointerId,
      recorder: createEditorPixelRecorder(layer.id, doc.width, doc.height),
      beforeSelection: captureEditorSelectionHistoryState(doc),
    };
    const bitmapBounds = drawEditorBrush(doc, point, tool, brush, strokeRef.current);
    doc.dirty = true;
    sync({ redrawBitmap: Boolean(bitmapBounds), bitmapBounds: bitmapBounds ?? undefined, status: "deferred" });
  };

  const movePointerEdit = (event: React.PointerEvent<HTMLDivElement>) => {
    const doc = documentRef.current;
    const canvas = canvasRef.current;
    if (!doc || !canvas) return;
    const point = readEditorPointer(event.nativeEvent, canvas, doc);
    pointerRef.current = point;
    if (tool === "rect-selection" && selectionDraftRef.current) {
      event.preventDefault();
      selectionDraftRef.current.current = point;
      doc.selection = buildRectSelectionMask(doc.width, doc.height, readSelectionFromDraft(selectionDraftRef.current));
      sync({ redrawBitmap: false, status: "deferred" });
      return;
    }
    if (tool === "lasso-selection" && lassoDraftRef.current?.pointerId === event.pointerId) {
      event.preventDefault();
      lassoDraftRef.current.path = appendLassoPoint(lassoDraftRef.current.path, point);
      sync({ redrawBitmap: false, status: "deferred" });
      return;
    }
    if (tool === "move-selection" && moveDraftRef.current?.pointerId === event.pointerId && doc.floatingSelection) {
      event.preventDefault();
      const previousBounds = { ...doc.floatingSelection.bounds };
      const dx = Math.round(point.x - moveDraftRef.current.start.x);
      const dy = Math.round(point.y - moveDraftRef.current.start.y);
      doc.floatingSelection.bounds = {
        ...moveDraftRef.current.initialBounds,
        x: Math.round(clamp(moveDraftRef.current.initialBounds.x + dx, -doc.floatingSelection.bounds.width + 1, doc.width - 1)),
        y: Math.round(clamp(moveDraftRef.current.initialBounds.y + dy, -doc.floatingSelection.bounds.height + 1, doc.height - 1)),
      };
      sync({ redrawBitmap: true, bitmapBounds: unionEditorBounds(previousBounds, doc.floatingSelection.bounds), status: "deferred" });
      return;
    }
    if (strokeRef.current && strokeRef.current.pointerId === event.pointerId && ["brush", "eraser", "restore"].includes(tool)) {
      event.preventDefault();
      const bitmapBounds = drawEditorBrush(doc, point, tool, brush, strokeRef.current);
      doc.dirty = true;
      sync({ redrawBitmap: Boolean(bitmapBounds), bitmapBounds: bitmapBounds ?? undefined, status: "deferred" });
      return;
    }
    sync({ redrawBitmap: false, status: "deferred" });
  };

  const endPointerEdit = (event: React.PointerEvent<HTMLDivElement>) => {
    const doc = documentRef.current;
    if (!doc) return;
    if (selectionDraftRef.current) {
      const before = selectionDraftRef.current.before;
      selectionDraftRef.current = null;
      commitSelectionChange("矩形选区", before, { redrawBitmap: false });
      return;
    }
    if (lassoDraftRef.current?.pointerId === event.pointerId) {
      const before = lassoDraftRef.current.before;
      doc.selection = buildLassoSelectionMask(doc.width, doc.height, lassoDraftRef.current.path);
      lassoDraftRef.current = null;
      commitSelectionChange("套索选区", before, { redrawBitmap: false });
      return;
    }
    if (moveDraftRef.current?.pointerId === event.pointerId) {
      const draft = moveDraftRef.current;
      const floatingBounds = doc.floatingSelection ? { ...doc.floatingSelection.bounds } : draft.historyBounds;
      const expanded = expandEditorPixelHistoryState(doc, draft.layerId, draft.historyBounds, draft.before, floatingBounds);
      pasteFloatingSelection(doc);
      moveDraftRef.current = null;
      if (expanded) commitPixelChange("移动选区", draft.layerId, expanded.bounds, expanded.before);
      return;
    }
    const stroke = strokeRef.current;
    if (!stroke || stroke.pointerId !== event.pointerId) return;
    strokeRef.current = null;
    const states = buildEditorStrokeHistoryStates(doc, stroke.recorder, stroke.beforeSelection);
    if (!states) {
      sync({ redrawBitmap: false, status: "immediate" });
      return;
    }
    const title = tool === "eraser" ? "橡皮" : tool === "restore" ? "恢复笔" : "画笔";
    commitHistoryEntry({
      ...createHistoryMetadata(title, true),
      kind: "pixels",
      ...states,
    });
  };

  const doc = documentRef.current;
  const showExportBackground = exportBackgroundMode === "color";
  const documentClassName = [
    "manual-editor-document",
    tool === "pan" ? "" : "no-pan",
    gridVisible ? "pixel-grid-visible" : "",
    showExportBackground ? "solid-background" : transparentBackgroundVisible ? "" : "transparent-background-hidden",
  ]
    .filter(Boolean)
    .join(" ");
  const documentStyle = doc
    ? {
        width: doc.width,
        height: doc.height,
        aspectRatio: `${doc.width} / ${doc.height}`,
        ...(showExportBackground ? { backgroundColor: exportBackgroundColor } : {}),
      }
    : undefined;

  return (
    <div
      className={documentClassName}
      style={documentStyle}
      onPointerDown={startPointerEdit}
      onPointerMove={movePointerEdit}
      onPointerUp={endPointerEdit}
      onPointerCancel={endPointerEdit}
      onPointerLeave={() => {
        pointerRef.current = null;
        lassoDraftRef.current = null;
        sync({ redrawBitmap: false, status: "immediate" });
      }}
    >
      <canvas ref={canvasRef} className="manual-editor-canvas" />
      <canvas ref={overlayRef} className="manual-editor-overlay" />
    </div>
  );
});

async function readSourceBlob(source: ManualEditSource, signal: AbortSignal) {
  if (source.blob) {
    return source.blob;
  }
  const response = await fetch(source.url, { signal });
  if (!response.ok) {
    throw new Error("图片读取失败。");
  }
  return response.blob();
}

function trimEditorHistory(entries: EditorHistoryEntry[]) {
  let next = entries.slice(-EDITOR_HISTORY_LIMIT);

  // 局部操作通常只占脏区大小，结构操作仍会持有整图快照。
  // 按唯一像素缓冲估算预算，共享原图只计算一次，超限时从最旧记录开始回收。
  while (next.length > 1 && estimateEditorHistoryBytes(next) > EDITOR_HISTORY_MEMORY_LIMIT_BYTES) {
    next = next.slice(1);
  }
  return next;
}

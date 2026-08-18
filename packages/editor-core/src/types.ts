export type EditorTool =
  | "pan"
  | "brush"
  | "eraser"
  | "restore"
  | "picker"
  | "rect-selection"
  | "lasso-selection"
  | "magic-wand"
  | "move-selection";

export type EditorSelection = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type EditorSelectionMask = {
  kind: "rect" | "lasso" | "magic";
  bounds: EditorSelection;
  mask: Uint8ClampedArray;
  path?: Array<{ x: number; y: number }>;
};

export type EditorBrushSettings = {
  size: number;
  hardness: number;
  opacity: number;
  color: string;
  hardEraser: boolean;
};

export type EditorBrushPreset = {
  id: string;
  name: string;
  settings: EditorBrushSettings;
};

export type EditorLayer = {
  id: string;
  name: string;
  visible: boolean;
  opacity: number;
  imageData: ImageData;
};

export type EditorClipboardItem = {
  name: string;
  imageData: ImageData;
  bounds: EditorSelection;
};

export type EditorSnapshot = {
  id: string;
  title: string;
  createdAt: number;
  width: number;
  height: number;
  /** The original image is read-only during editing, so snapshots share it instead of duplicating the same pixels. */
  originalImageData: ImageData;
  layers: EditorLayer[];
  activeLayerId: string;
  selection: EditorSelectionMask | null;
  floatingSelection: EditorClipboardItem | null;
};

/** Lightweight history state for selection and floating-content changes. */
export type EditorSelectionHistoryState = {
  activeLayerId: string;
  selection: EditorSelectionMask | null;
  floatingSelection: EditorClipboardItem | null;
};

/** Local pixels from one layer plus related selection state, used for brush and localized pixel edits. */
export type EditorPixelHistoryState = EditorSelectionHistoryState & {
  pixels: ImageData;
};

/** Layer order and presentation state that does not duplicate pixel data. */
export type EditorLayerHistoryState = {
  activeLayerId: string;
  layers: Array<Pick<EditorLayer, "id" | "name" | "visible" | "opacity">>;
};

type EditorHistoryMetadata = {
  id: string;
  title: string;
  createdAt: number;
  /** Whether undo or redo must redraw the bitmap; selection-only and rename changes update overlays or state. */
  redrawBitmap: boolean;
  /** Whether the operation changes canvas dimensions and requires the outer layout to recalculate the document. */
  layout: boolean;
};

export type EditorHistoryEntry = EditorHistoryMetadata & (
  | { kind: "snapshot"; before: EditorSnapshot; after: EditorSnapshot }
  | { kind: "selection"; before: EditorSelectionHistoryState; after: EditorSelectionHistoryState }
  | { kind: "pixels"; layerId: string; bounds: EditorSelection; before: EditorPixelHistoryState; after: EditorPixelHistoryState }
  | { kind: "layers"; before: EditorLayerHistoryState; after: EditorLayerHistoryState }
);

export type EditorZoomPreviewMode = "off" | "loupe" | "panel" | "both";

export type EditorExportBackgroundMode = "transparent" | "color";

export type EditorExportOptions = {
  backgroundMode: EditorExportBackgroundMode;
  backgroundColor: string;
};

export type EditorDocument = {
  name: string;
  width: number;
  height: number;
  layers: EditorLayer[];
  activeLayerId: string;
  originalImageData: ImageData;
  selection: EditorSelectionMask | null;
  floatingSelection: EditorClipboardItem | null;
  dirty: boolean;
};

export type EditorStatus = {
  width: number;
  height: number;
  canUndo: boolean;
  canRedo: boolean;
  dirty: boolean;
  hasSelection: boolean;
  hasFloatingSelection: boolean;
  sample: string;
  layers: Array<Pick<EditorLayer, "id" | "name" | "visible" | "opacity"> & { active: boolean }>;
  history: Array<Pick<EditorHistoryEntry, "id" | "title" | "createdAt">>;
  snapshots: Array<Pick<EditorSnapshot, "id" | "title" | "createdAt">>;
  activeLayerId: string | null;
};

export type EditorStrokeState = {
  pointerId: number;
  recorder: EditorPixelRecorder;
  beforeSelection: EditorSelectionHistoryState;
};

/** Record each pixel only before its first change in a stroke, then compact the result into a rectangular dirty region. */
export type EditorPixelRecorder = {
  layerId: string;
  width: number;
  height: number;
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  beforePixels: Map<number, number>;
};

export type ImagePoint = { x: number; y: number };

export type EditorSelectionDraft = {
  start: ImagePoint;
  current: ImagePoint;
  before: EditorSelectionHistoryState;
};

export type EditorLassoDraft = {
  pointerId: number;
  before: EditorSelectionHistoryState;
  path: ImagePoint[];
};

export type EditorMoveDraft = {
  pointerId: number;
  layerId: string;
  before: EditorPixelHistoryState;
  start: ImagePoint;
  initialBounds: EditorSelection;
  historyBounds: EditorSelection;
};

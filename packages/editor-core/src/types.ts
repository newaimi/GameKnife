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
  /** 原始图片在编辑期间只读，快照共享该引用，避免每条历史重复保存同一份像素。 */
  originalImageData: ImageData;
  layers: EditorLayer[];
  activeLayerId: string;
  selection: EditorSelectionMask | null;
  floatingSelection: EditorClipboardItem | null;
};

/** 只影响选区和浮动内容的轻量历史状态。 */
export type EditorSelectionHistoryState = {
  activeLayerId: string;
  selection: EditorSelectionMask | null;
  floatingSelection: EditorClipboardItem | null;
};

/** 单个图层局部像素及其关联选区状态，用于画笔和局部像素编辑。 */
export type EditorPixelHistoryState = EditorSelectionHistoryState & {
  pixels: ImageData;
};

/** 不复制像素的图层顺序和展示属性状态。 */
export type EditorLayerHistoryState = {
  activeLayerId: string;
  layers: Array<Pick<EditorLayer, "id" | "name" | "visible" | "opacity">>;
};

type EditorHistoryMetadata = {
  id: string;
  title: string;
  createdAt: number;
  /** 撤销或重做后是否需要刷新位图；纯选区和重命名只刷新覆盖层或状态。 */
  redrawBitmap: boolean;
  /** 操作是否改变画布尺寸，用于通知外层重新计算文档布局。 */
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

/** 笔画期间只记录第一次被修改的像素，结束时再压缩为矩形脏区。 */
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

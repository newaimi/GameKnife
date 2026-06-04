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
  originalImageData: ImageData;
  layers: EditorLayer[];
  activeLayerId: string;
  selection: EditorSelectionMask | null;
  floatingSelection: EditorClipboardItem | null;
};

export type EditorHistoryEntry = {
  id: string;
  title: string;
  createdAt: number;
  before: EditorSnapshot;
  after: EditorSnapshot;
};

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
  before: EditorSnapshot;
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
};

export type ImagePoint = { x: number; y: number };

export type EditorSelectionDraft = {
  start: ImagePoint;
  current: ImagePoint;
  before: EditorSnapshot;
};

export type EditorLassoDraft = {
  pointerId: number;
  before: EditorSnapshot;
  path: ImagePoint[];
};

export type EditorMoveDraft = {
  pointerId: number;
  before: EditorSnapshot;
  start: ImagePoint;
  initialBounds: EditorSelection;
};

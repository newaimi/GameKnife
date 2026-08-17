import type {
  EditorExportOptions,
  EditorHistoryEntry,
  EditorLayer,
  EditorPixelHistoryState,
  EditorPixelRecorder,
  EditorSelection,
  EditorSelectionHistoryState,
  EditorSnapshot,
} from "@gameknife/editor-core";

export type ManualEditorHandle = {
  exportPngBlob: (options?: EditorExportOptions) => Promise<Blob>;
  markSaved: () => void;
  undo: () => void;
  redo: () => void;
  clearSelection: () => void;
  deleteSelection: () => void;
  copySelection: () => Promise<void>;
  cutSelection: () => Promise<void>;
  pasteSelection: () => Promise<void>;
  commitFloatingSelection: () => void;
  cropSelection: () => void;
  createLayer: () => void;
  duplicateLayer: () => void;
  deleteLayer: (layerId: string) => void;
  setActiveLayer: (layerId: string) => void;
  updateLayerName: (layerId: string, name: string) => void;
  updateLayerOpacity: (layerId: string, opacity: number) => void;
  previewLayerOpacity: (layerId: string, opacity: number) => void;
  commitLayerOpacity: (layerId: string) => void;
  toggleLayerVisibility: (layerId: string) => void;
  moveLayer: (layerId: string, direction: "up" | "down") => void;
  mergeLayerDown: (layerId: string) => void;
  flattenLayers: () => void;
  jumpToHistory: (index: number) => void;
  createSnapshot: () => void;
  restoreSnapshot: (snapshotId: string) => void;
  trimTransparent: () => void;
  addPadding: (padding: number) => void;
  flipHorizontal: () => void;
  flipVertical: () => void;
  rotateClockwise: () => void;
  applyAlphaThreshold: (threshold: number) => void;
  removeAlphaNoise: () => void;
  contractAlpha: (amount: number) => void;
  expandAlpha: (amount: number) => void;
  featherAlpha: (radius: number) => void;
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

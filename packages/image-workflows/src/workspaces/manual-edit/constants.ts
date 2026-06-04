import type { EditorBrushPreset, EditorBrushSettings } from "@gameknife/editor-core";

export const EDITOR_HISTORY_LIMIT = 32;
export const EDITOR_HISTORY_MEMORY_LIMIT_BYTES = 256 * 1024 * 1024;
export const EDITOR_SNAPSHOT_LIMIT = 5;

export const EDITOR_DEFAULT_BRUSH: EditorBrushSettings = {
  size: 18,
  hardness: 75,
  opacity: 100,
  color: "#1f6fff",
  hardEraser: false,
};

export const EDITOR_BRUSH_PRESETS: EditorBrushPreset[] = [
  { id: "detail", name: "细节", settings: { size: 6, hardness: 92, opacity: 100, color: "#1f6fff", hardEraser: false } },
  { id: "paint", name: "上色", settings: { size: 18, hardness: 70, opacity: 100, color: "#1f6fff", hardEraser: false } },
  { id: "soft", name: "柔边", settings: { size: 34, hardness: 28, opacity: 65, color: "#1f6fff", hardEraser: false } },
  { id: "pixel", name: "像素", settings: { size: 1, hardness: 100, opacity: 100, color: "#1f6fff", hardEraser: true } },
];

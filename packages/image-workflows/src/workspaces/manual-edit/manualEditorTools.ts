import type { ComponentType } from "react";
import { Brush, Eraser, Lasso, MousePointer2, Pipette, SquareDashedMousePointer, Undo2, Wand } from "lucide-react";
import type { EditorTool } from "@gameknife/editor-core";

export type ManualEditorToolInfo = {
  tool: EditorTool;
  translationKey: string;
  shortcut: string;
  icon: ComponentType<{ size?: number; strokeWidth?: number }>;
};

/**
 * Keeps tool identifiers, shortcuts, and icons aligned between the rail and inspector.
 * Labels and descriptions remain in locale resources while EditorCanvas owns execution.
 */
export const MANUAL_EDITOR_TOOLS: ManualEditorToolInfo[] = [
  { tool: "pan", translationKey: "pan", shortcut: "V", icon: MousePointer2 },
  { tool: "move-selection", translationKey: "moveSelection", shortcut: "M", icon: MousePointer2 },
  { tool: "rect-selection", translationKey: "rectSelection", shortcut: "C", icon: SquareDashedMousePointer },
  { tool: "lasso-selection", translationKey: "lassoSelection", shortcut: "L", icon: Lasso },
  { tool: "magic-wand", translationKey: "magicWand", shortcut: "W", icon: Wand },
  { tool: "brush", translationKey: "brush", shortcut: "B", icon: Brush },
  { tool: "eraser", translationKey: "eraser", shortcut: "E", icon: Eraser },
  { tool: "picker", translationKey: "picker", shortcut: "I", icon: Pipette },
  { tool: "restore", translationKey: "restore", shortcut: "R", icon: Undo2 },
];

export function readManualEditorToolInfo(tool: EditorTool) {
  return MANUAL_EDITOR_TOOLS.find((item) => item.tool === tool) ?? MANUAL_EDITOR_TOOLS[5];
}

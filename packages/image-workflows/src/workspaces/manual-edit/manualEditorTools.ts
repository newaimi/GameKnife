import type { ComponentType } from "react";
import { Brush, Eraser, Lasso, MousePointer2, Pipette, SquareDashedMousePointer, Undo2, Wand } from "lucide-react";
import type { EditorTool } from "@gameknife/editor-core";

export type ManualEditorToolInfo = {
  tool: EditorTool;
  label: string;
  shortcut: string;
  description: string;
  icon: ComponentType<{ size?: number; strokeWidth?: number }>;
};

/**
 * 工具名称、快捷键和说明需要在工具栏与检查器中保持同一口径，因此集中为一份只读定义。
 * 工具执行逻辑仍由 EditorCanvas 处理，这里只描述用户可见的选择项。
 */
export const MANUAL_EDITOR_TOOLS: ManualEditorToolInfo[] = [
  { tool: "pan", label: "移动画布", shortcut: "V", description: "拖动画布查看细节，适合放大后移动位置。", icon: MousePointer2 },
  { tool: "move-selection", label: "移动选区", shortcut: "M", description: "拖动已有选区或浮动内容，调整后点击“贴入”确认。", icon: MousePointer2 },
  { tool: "rect-selection", label: "矩形选区", shortcut: "C", description: "拖出矩形范围，再执行复制、剪切、删除或裁切。", icon: SquareDashedMousePointer },
  { tool: "lasso-selection", label: "套索", shortcut: "L", description: "沿素材边缘拖出自由选区，适合不规则小组件。", icon: Lasso },
  { tool: "magic-wand", label: "魔棒", shortcut: "W", description: "点击相近颜色或透明区域生成选区，容差越高选得越宽。", icon: Wand },
  { tool: "brush", label: "画笔", shortcut: "B", description: "在当前图层绘制颜色。先选颜色，再按需要调整大小和硬度。", icon: Brush },
  { tool: "eraser", label: "橡皮", shortcut: "E", description: "擦除当前图层像素。硬边适合像素图，柔边适合抠图边缘。", icon: Eraser },
  { tool: "picker", label: "吸管", shortcut: "I", description: "点击图片取色，取到的颜色会用于画笔。", icon: Pipette },
  { tool: "restore", label: "恢复", shortcut: "R", description: "从导入时的原图恢复像素，适合修回误擦区域。", icon: Undo2 },
];

export function readManualEditorToolInfo(tool: EditorTool) {
  return MANUAL_EDITOR_TOOLS.find((item) => item.tool === tool) ?? MANUAL_EDITOR_TOOLS[5];
}

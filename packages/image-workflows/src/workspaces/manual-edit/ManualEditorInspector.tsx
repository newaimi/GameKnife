import type { Dispatch, RefObject, SetStateAction } from "react";
import type { EditorBrushSettings, EditorExportBackgroundMode, EditorTool, EditorZoomPreviewMode } from "@gameknife/editor-core";
import { Button, NumberField } from "@gameknife/ui-kit";
import { EDITOR_BRUSH_PRESETS } from "./constants";
import { ManualEditorHistoryPanel } from "./ManualEditorHistoryPanel";
import { ManualEditorLayersPanel } from "./ManualEditorLayersPanel";
import { readManualEditorToolInfo } from "./manualEditorTools";
import type { EditorStatus, ManualEditorHandle } from "./types";

const BACKGROUND_PRESETS = ["#ffffff", "#f5f7fb", "#d7ecff", "#ff3b30", "#1f6fff"];

export function ManualEditorInspector({
  editorRef,
  hasSource,
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
  alphaThreshold,
  edgeAmount,
  featherRadius,
  padding,
  status,
  sourceName,
  saveMessage,
  onBrushChange,
  onGridVisibleChange,
  onTransparentBackgroundVisibleChange,
  onExportBackgroundModeChange,
  onExportBackgroundColorChange,
  onMagicToleranceChange,
  onMagicAlphaToleranceChange,
  onMagicContiguousChange,
  onZoomPreviewModeChange,
  onAlphaThresholdChange,
  onEdgeAmountChange,
  onFeatherRadiusChange,
  onPaddingChange,
}: {
  editorRef: RefObject<ManualEditorHandle | null>;
  hasSource: boolean;
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
  alphaThreshold: number;
  edgeAmount: number;
  featherRadius: number;
  padding: number;
  status: EditorStatus;
  sourceName?: string;
  saveMessage: string;
  onBrushChange: Dispatch<SetStateAction<EditorBrushSettings>>;
  onGridVisibleChange: (visible: boolean) => void;
  onTransparentBackgroundVisibleChange: (visible: boolean) => void;
  onExportBackgroundModeChange: (mode: EditorExportBackgroundMode) => void;
  onExportBackgroundColorChange: (color: string) => void;
  onMagicToleranceChange: (value: number) => void;
  onMagicAlphaToleranceChange: (value: number) => void;
  onMagicContiguousChange: (contiguous: boolean) => void;
  onZoomPreviewModeChange: (mode: EditorZoomPreviewMode) => void;
  onAlphaThresholdChange: (value: number) => void;
  onEdgeAmountChange: (value: number) => void;
  onFeatherRadiusChange: (value: number) => void;
  onPaddingChange: (value: number) => void;
}) {
  const activeToolInfo = readManualEditorToolInfo(tool);
  const showBrushControls = tool === "brush" || tool === "eraser" || tool === "restore";
  const showMagicControls = tool === "magic-wand";

  return (
    <aside className="manual-editor-inspector">
      <div className="editor-section manual-editor-status">
        <strong>{sourceName ?? "未导入图片"}</strong>
        <span>
          {status.width || "-"}×{status.height || "-"} · {status.dirty ? "未保存" : "已同步"} · {status.sample}
        </span>
        {saveMessage ? <span>{saveMessage}</span> : null}
      </div>

      <div className="editor-section editor-tool-context">
        <div className="editor-section-heading">
          <div>
            <span>当前工具</span>
            <strong>{activeToolInfo.label}</strong>
          </div>
          <em>{activeToolInfo.shortcut}</em>
        </div>

        {showBrushControls ? (
          <>
            <NumberField label="大小" value={brush.size} min={1} max={160} onChange={(size) => onBrushChange((current) => ({ ...current, size }))} />
            <NumberField label="硬度" value={brush.hardness} min={1} max={100} onChange={(hardness) => onBrushChange((current) => ({ ...current, hardness }))} />
            <NumberField
              label={tool === "restore" ? "恢复强度" : "不透明度"}
              value={brush.opacity}
              min={1}
              max={100}
              onChange={(opacity) => onBrushChange((current) => ({ ...current, opacity }))}
            />
          </>
        ) : null}

        {tool === "brush" ? (
          <label className="number-field">
            <span>颜色</span>
            <input type="color" value={brush.color} onChange={(event) => onBrushChange((current) => ({ ...current, color: event.target.value }))} />
          </label>
        ) : null}

        {tool === "eraser" ? (
          <label className="setting-check">
            <input type="checkbox" checked={brush.hardEraser} onChange={(event) => onBrushChange((current) => ({ ...current, hardEraser: event.target.checked }))} />
            橡皮硬边
          </label>
        ) : null}

        {showMagicControls ? (
          <>
            <NumberField label="颜色容差" value={magicTolerance} min={0} max={255} onChange={onMagicToleranceChange} />
            <NumberField label="Alpha 容差" value={magicAlphaTolerance} min={0} max={255} onChange={onMagicAlphaToleranceChange} />
            <label className="setting-check">
              <input type="checkbox" checked={magicContiguous} onChange={(event) => onMagicContiguousChange(event.target.checked)} />
              只选连续区域
            </label>
          </>
        ) : null}
      </div>

      {showBrushControls ? (
        <div className="editor-section">
          <div className="editor-section-heading compact">
            <strong>笔刷手感</strong>
          </div>
          <div className="editor-preset-grid">
            {EDITOR_BRUSH_PRESETS.map((preset) => (
              <Button size="small" key={preset.id} onClick={() => onBrushChange({ ...preset.settings, color: brush.color })}>
                {preset.name}
              </Button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="editor-section">
        <div className="editor-section-heading compact">
          <strong>视图</strong>
        </div>
        <div className="editor-toggle-grid">
          <label className="setting-check">
            <input type="checkbox" checked={gridVisible} onChange={(event) => onGridVisibleChange(event.target.checked)} />
            格线
          </label>
          <label className="setting-check">
            <input type="checkbox" checked={transparentBackgroundVisible} onChange={(event) => onTransparentBackgroundVisibleChange(event.target.checked)} />
            透明底色
          </label>
        </div>
        <label className="number-field">
          <span>局部预览</span>
          <select value={zoomPreviewMode} onChange={(event) => onZoomPreviewModeChange(event.target.value as EditorZoomPreviewMode)}>
            <option value="off">关闭</option>
            <option value="loupe">放大镜</option>
            <option value="panel">固定小窗</option>
            <option value="both">同时显示</option>
          </select>
        </label>
      </div>

      <div className="editor-section">
        <div className="editor-section-heading compact">
          <strong>导出</strong>
        </div>
        <label className="number-field">
          <span>导出背景</span>
          <select value={exportBackgroundMode} onChange={(event) => onExportBackgroundModeChange(event.target.value as EditorExportBackgroundMode)}>
            <option value="transparent">透明背景</option>
            <option value="color">颜色背景</option>
          </select>
        </label>
        {exportBackgroundMode === "color" ? (
          <label className="number-field">
            <span>背景颜色</span>
            <div className="background-color-field">
              <input type="color" value={exportBackgroundColor} onChange={(event) => onExportBackgroundColorChange(event.target.value)} aria-label="选择导出背景颜色" />
              <span>{exportBackgroundColor.toUpperCase()}</span>
            </div>
            <div className="background-color-presets" aria-label="导出背景颜色预设">
              {BACKGROUND_PRESETS.map((color) => (
                <button
                  key={color}
                  className={exportBackgroundColor.toLowerCase() === color ? "active" : ""}
                  type="button"
                  style={{ backgroundColor: color }}
                  aria-label={`使用 ${color} 作为导出背景颜色`}
                  onClick={() => onExportBackgroundColorChange(color)}
                />
              ))}
            </div>
          </label>
        ) : null}
      </div>

      <div className="editor-section">
        <strong>选区</strong>
        <div className="editor-action-row">
          <Button size="small" disabled={!status.hasSelection} onClick={() => editorRef.current?.deleteSelection()}>删除</Button>
          <Button size="small" disabled={!status.hasSelection} onClick={() => void editorRef.current?.copySelection()}>复制</Button>
          <Button size="small" disabled={!status.hasSelection} onClick={() => void editorRef.current?.cutSelection()}>剪切</Button>
          <Button size="small" disabled={!hasSource} onClick={() => void editorRef.current?.pasteSelection()}>粘贴</Button>
          <Button size="small" disabled={!status.hasFloatingSelection} onClick={() => editorRef.current?.commitFloatingSelection()}>贴入</Button>
          <Button size="small" disabled={!status.hasSelection} onClick={() => editorRef.current?.cropSelection()}>裁到选区</Button>
          <Button size="small" disabled={!status.hasSelection} onClick={() => editorRef.current?.clearSelection()}>清除选区</Button>
        </div>
      </div>

      <ManualEditorLayersPanel editorRef={editorRef} status={status} hasSource={hasSource} />
      <ManualEditorHistoryPanel editorRef={editorRef} status={status} hasSource={hasSource} />

      <div className="editor-section">
        <strong>修边</strong>
        <NumberField label="Alpha 阈值" value={alphaThreshold} min={0} max={255} onChange={onAlphaThresholdChange} />
        <NumberField label="边缘像素" value={edgeAmount} min={1} max={8} onChange={onEdgeAmountChange} />
        <NumberField label="羽化半径" value={featherRadius} min={1} max={8} onChange={onFeatherRadiusChange} />
        <div className="editor-action-row">
          <Button size="small" disabled={!hasSource} onClick={() => editorRef.current?.applyAlphaThreshold(alphaThreshold)}>阈值</Button>
          <Button size="small" disabled={!hasSource} onClick={() => editorRef.current?.removeAlphaNoise()}>去噪点</Button>
          <Button size="small" disabled={!hasSource} onClick={() => editorRef.current?.contractAlpha(edgeAmount)}>收缩</Button>
          <Button size="small" disabled={!hasSource} onClick={() => editorRef.current?.expandAlpha(edgeAmount)}>扩张</Button>
          <Button size="small" disabled={!hasSource} onClick={() => editorRef.current?.featherAlpha(featherRadius)}>羽化</Button>
        </div>
      </div>

      <div className="editor-section">
        <strong>画布</strong>
        <NumberField label="留边" value={padding} min={0} max={256} onChange={onPaddingChange} />
        <div className="editor-action-row">
          <Button size="small" disabled={!hasSource} onClick={() => editorRef.current?.trimTransparent()}>裁透明边</Button>
          <Button size="small" disabled={!hasSource} onClick={() => editorRef.current?.addPadding(padding)}>加留边</Button>
          <Button size="small" disabled={!hasSource} onClick={() => editorRef.current?.flipHorizontal()}>水平翻转</Button>
          <Button size="small" disabled={!hasSource} onClick={() => editorRef.current?.flipVertical()}>垂直翻转</Button>
          <Button size="small" disabled={!hasSource} onClick={() => editorRef.current?.rotateClockwise()}>旋转90</Button>
        </div>
      </div>

    </aside>
  );
}

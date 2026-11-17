import type { Dispatch, RefObject, SetStateAction } from "react";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation("manualEditor");
  const activeToolInfo = readManualEditorToolInfo(tool);
  const showBrushControls = tool === "brush" || tool === "eraser" || tool === "restore";
  const showMagicControls = tool === "magic-wand";

  return (
    <aside className="manual-editor-inspector">
      <div className="editor-section manual-editor-status">
        <strong>{sourceName ?? t("status.noImage")}</strong>
        <span>
          {status.width || "-"}×{status.height || "-"} · {status.dirty ? t("status.unsaved") : t("status.synced")} · {status.sample}
        </span>
        {saveMessage ? <span>{saveMessage}</span> : null}
      </div>

      <div className="editor-section editor-tool-context">
        <div className="editor-section-heading">
          <div>
            <span>{t("inspector.currentTool")}</span>
            <strong>{t(`tools.${activeToolInfo.translationKey}.label`)}</strong>
          </div>
          <em>{activeToolInfo.shortcut}</em>
        </div>

        {showBrushControls ? (
          <>
            <NumberField label={t("inspector.size")} value={brush.size} min={1} max={160} onChange={(size) => onBrushChange((current) => ({ ...current, size }))} />
            <NumberField label={t("inspector.hardness")} value={brush.hardness} min={1} max={100} onChange={(hardness) => onBrushChange((current) => ({ ...current, hardness }))} />
            <NumberField
              label={tool === "restore" ? t("inspector.restoreStrength") : t("inspector.opacity")}
              value={brush.opacity}
              min={1}
              max={100}
              onChange={(opacity) => onBrushChange((current) => ({ ...current, opacity }))}
            />
          </>
        ) : null}

        {tool === "brush" ? (
          <label className="number-field">
            <span>{t("inspector.color")}</span>
            <input type="color" value={brush.color} onChange={(event) => onBrushChange((current) => ({ ...current, color: event.target.value }))} />
          </label>
        ) : null}

        {tool === "eraser" ? (
          <label className="setting-check">
            <input type="checkbox" checked={brush.hardEraser} onChange={(event) => onBrushChange((current) => ({ ...current, hardEraser: event.target.checked }))} />
            {t("inspector.hardEraser")}
          </label>
        ) : null}

        {showMagicControls ? (
          <>
            <NumberField label={t("inspector.colorTolerance")} value={magicTolerance} min={0} max={255} onChange={onMagicToleranceChange} />
            <NumberField label={t("inspector.alphaTolerance")} value={magicAlphaTolerance} min={0} max={255} onChange={onMagicAlphaToleranceChange} />
            <label className="setting-check">
              <input type="checkbox" checked={magicContiguous} onChange={(event) => onMagicContiguousChange(event.target.checked)} />
              {t("inspector.contiguousOnly")}
            </label>
          </>
        ) : null}
      </div>

      {showBrushControls ? (
        <div className="editor-section">
          <div className="editor-section-heading compact">
            <strong>{t("inspector.brushFeel")}</strong>
          </div>
          <div className="editor-preset-grid">
            {EDITOR_BRUSH_PRESETS.map((preset) => (
              <Button size="small" key={preset.id} onClick={() => onBrushChange({ ...preset.settings, color: brush.color })}>
                {t(`presets.${preset.id}`)}
              </Button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="editor-section">
        <div className="editor-section-heading compact">
          <strong>{t("inspector.view")}</strong>
        </div>
        <div className="editor-toggle-grid">
          <label className="setting-check">
            <input type="checkbox" checked={gridVisible} onChange={(event) => onGridVisibleChange(event.target.checked)} />
            {t("inspector.grid")}
          </label>
          <label className="setting-check">
            <input type="checkbox" checked={transparentBackgroundVisible} onChange={(event) => onTransparentBackgroundVisibleChange(event.target.checked)} />
            {t("inspector.transparentBackground")}
          </label>
        </div>
        <label className="number-field">
          <span>{t("inspector.localPreview")}</span>
          <select value={zoomPreviewMode} onChange={(event) => onZoomPreviewModeChange(event.target.value as EditorZoomPreviewMode)}>
            <option value="off">{t("inspector.previewOff")}</option>
            <option value="loupe">{t("inspector.previewLoupe")}</option>
            <option value="panel">{t("inspector.previewPanel")}</option>
            <option value="both">{t("inspector.previewBoth")}</option>
          </select>
        </label>
      </div>

      <div className="editor-section">
        <div className="editor-section-heading compact">
          <strong>{t("inspector.export")}</strong>
        </div>
        <label className="number-field">
          <span>{t("inspector.exportBackground")}</span>
          <select value={exportBackgroundMode} onChange={(event) => onExportBackgroundModeChange(event.target.value as EditorExportBackgroundMode)}>
            <option value="transparent">{t("inspector.transparent")}</option>
            <option value="color">{t("inspector.colorBackground")}</option>
          </select>
        </label>
        {exportBackgroundMode === "color" ? (
          <label className="number-field">
            <span>{t("inspector.backgroundColor")}</span>
            <div className="background-color-field">
              <input type="color" value={exportBackgroundColor} onChange={(event) => onExportBackgroundColorChange(event.target.value)} aria-label={t("inspector.chooseBackgroundColor")} />
              <span>{exportBackgroundColor.toUpperCase()}</span>
            </div>
            <div className="background-color-presets" aria-label={t("inspector.backgroundPresets")}>
              {BACKGROUND_PRESETS.map((color) => (
                <button
                  key={color}
                  className={exportBackgroundColor.toLowerCase() === color ? "active" : ""}
                  type="button"
                  style={{ backgroundColor: color }}
                  aria-label={t("inspector.useBackgroundColor", { color })}
                  onClick={() => onExportBackgroundColorChange(color)}
                />
              ))}
            </div>
          </label>
        ) : null}
      </div>

      <div className="editor-section">
        <strong>{t("inspector.selection")}</strong>
        <div className="editor-action-row">
          <Button size="small" disabled={!status.hasSelection} onClick={() => editorRef.current?.deleteSelection()}>{t("inspector.delete")}</Button>
          <Button size="small" disabled={!status.hasSelection} onClick={() => void editorRef.current?.copySelection()}>{t("inspector.copy")}</Button>
          <Button size="small" disabled={!status.hasSelection} onClick={() => void editorRef.current?.cutSelection()}>{t("inspector.cut")}</Button>
          <Button size="small" disabled={!hasSource} onClick={() => void editorRef.current?.pasteSelection()}>{t("inspector.paste")}</Button>
          <Button size="small" disabled={!status.hasFloatingSelection} onClick={() => editorRef.current?.commitFloatingSelection()}>{t("inspector.commit")}</Button>
          <Button size="small" disabled={!status.hasSelection} onClick={() => editorRef.current?.cropSelection()}>{t("inspector.cropToSelection")}</Button>
          <Button size="small" disabled={!status.hasSelection} onClick={() => editorRef.current?.clearSelection()}>{t("inspector.clearSelection")}</Button>
        </div>
      </div>

      <ManualEditorLayersPanel editorRef={editorRef} status={status} hasSource={hasSource} />
      <ManualEditorHistoryPanel editorRef={editorRef} status={status} hasSource={hasSource} />

      <div className="editor-section">
        <strong>{t("inspector.edgeCleanup")}</strong>
        <NumberField label={t("inspector.alphaThreshold")} value={alphaThreshold} min={0} max={255} onChange={onAlphaThresholdChange} />
        <NumberField label={t("inspector.edgePixels")} value={edgeAmount} min={1} max={8} onChange={onEdgeAmountChange} />
        <NumberField label={t("inspector.featherRadius")} value={featherRadius} min={1} max={8} onChange={onFeatherRadiusChange} />
        <div className="editor-action-row">
          <Button size="small" disabled={!hasSource} onClick={() => editorRef.current?.applyAlphaThreshold(alphaThreshold)}>{t("inspector.threshold")}</Button>
          <Button size="small" disabled={!hasSource} onClick={() => editorRef.current?.removeAlphaNoise()}>{t("inspector.removeNoise")}</Button>
          <Button size="small" disabled={!hasSource} onClick={() => editorRef.current?.contractAlpha(edgeAmount)}>{t("inspector.contract")}</Button>
          <Button size="small" disabled={!hasSource} onClick={() => editorRef.current?.expandAlpha(edgeAmount)}>{t("inspector.expand")}</Button>
          <Button size="small" disabled={!hasSource} onClick={() => editorRef.current?.featherAlpha(featherRadius)}>{t("inspector.feather")}</Button>
        </div>
      </div>

      <div className="editor-section">
        <strong>{t("inspector.canvas")}</strong>
        <NumberField label={t("inspector.padding")} value={padding} min={0} max={256} onChange={onPaddingChange} />
        <div className="editor-action-row">
          <Button size="small" disabled={!hasSource} onClick={() => editorRef.current?.trimTransparent()}>{t("inspector.trimTransparent")}</Button>
          <Button size="small" disabled={!hasSource} onClick={() => editorRef.current?.addPadding(padding)}>{t("inspector.addPadding")}</Button>
          <Button size="small" disabled={!hasSource} onClick={() => editorRef.current?.flipHorizontal()}>{t("inspector.flipHorizontal")}</Button>
          <Button size="small" disabled={!hasSource} onClick={() => editorRef.current?.flipVertical()}>{t("inspector.flipVertical")}</Button>
          <Button size="small" disabled={!hasSource} onClick={() => editorRef.current?.rotateClockwise()}>{t("inspector.rotateClockwise")}</Button>
        </div>
      </div>

    </aside>
  );
}

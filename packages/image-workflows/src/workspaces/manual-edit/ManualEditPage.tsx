import { gameKnifeApiClient } from "@gameknife/api-client";
import React, { useEffect, useRef, useState } from "react";
import type { EditorBrushSettings, EditorExportBackgroundMode, EditorExportOptions, EditorTool, EditorZoomPreviewMode } from "@gameknife/editor-core";
import type { FailureDialogState, ManualEditSource } from "../../types/manualEdit";
import { buildImageDownloadName, downloadBlob } from "../../utils/downloads";
import { EDITOR_DEFAULT_BRUSH } from "./constants";
import { ManualEditorInspector } from "./ManualEditorInspector";
import { ManualEditorLayout } from "./ManualEditorLayout";
import { ManualEditorStage } from "./ManualEditorStage";
import { ManualEditorToolRail } from "./ManualEditorToolRail";
import type { EditorStatus, ManualEditorHandle } from "./types";

/**
 * 手动编辑页面负责跨面板状态、资源导入和保存链路。工具导航、画布、检查器、图层与历史
 * 已拆到各自组件，避免局部输入状态和编辑器命令继续堆积在页面控制器中。
 */
export function ManualEditPage({
  source,
  gridVisible,
  canWrite,
  fileInput,
  onGridVisibleChange,
  onUpload,
  onFailure,
}: {
  source: ManualEditSource | null;
  gridVisible: boolean;
  canWrite: boolean;
  fileInput: React.RefObject<HTMLInputElement | null>;
  onGridVisibleChange: React.Dispatch<React.SetStateAction<boolean>>;
  onUpload: (file: File) => void;
  onFailure: React.Dispatch<React.SetStateAction<FailureDialogState | null>>;
}) {
  const editorRef = useRef<ManualEditorHandle | null>(null);
  const [tool, setTool] = useState<EditorTool>("brush");
  const [brush, setBrush] = useState<EditorBrushSettings>(EDITOR_DEFAULT_BRUSH);
  const [transparentBackgroundVisible, setTransparentBackgroundVisible] = useState(true);
  const [exportBackgroundMode, setExportBackgroundMode] = useState<EditorExportBackgroundMode>("transparent");
  const [exportBackgroundColor, setExportBackgroundColor] = useState("#ffffff");
  const [magicTolerance, setMagicTolerance] = useState(28);
  const [magicAlphaTolerance, setMagicAlphaTolerance] = useState(20);
  const [magicContiguous, setMagicContiguous] = useState(true);
  const [zoomPreviewMode, setZoomPreviewMode] = useState<EditorZoomPreviewMode>("off");
  const [alphaThreshold, setAlphaThreshold] = useState(16);
  const [edgeAmount, setEdgeAmount] = useState(1);
  const [featherRadius, setFeatherRadius] = useState(2);
  const [padding, setPadding] = useState(8);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState("");
  const [status, setStatus] = useState<EditorStatus>({
    width: 0,
    height: 0,
    canUndo: false,
    canRedo: false,
    dirty: false,
    hasSelection: false,
    hasFloatingSelection: false,
    sample: "-",
    layers: [],
    history: [],
    snapshots: [],
    activeLayerId: null,
  });

  useEffect(() => {
    setSaveMessage("");
    setTool("brush");
  }, [source?.url]);

  function importImage() {
    if (canWrite) fileInput.current?.click();
  }

  function readExportOptions(): EditorExportOptions {
    return {
      backgroundMode: exportBackgroundMode,
      backgroundColor: exportBackgroundColor,
    };
  }

  async function downloadEditedImage() {
    if (!source || !editorRef.current) return;
    try {
      const blob = await editorRef.current.exportPngBlob(readExportOptions());
      downloadBlob(blob, buildImageDownloadName(source.name || "manual-edit", blob));
    } catch (error) {
      onFailure({
        title: "图片下载失败",
        message: "手动编辑结果无法导出为 PNG。",
        detail: error instanceof Error ? error.message : "下载失败。",
      });
    }
  }

  async function saveEditedImage() {
    if (!source || !editorRef.current || saving || !canWrite) return;
    setSaving(true);
    setSaveMessage("");
    try {
      const blob = await editorRef.current.exportPngBlob(readExportOptions());
      const filename = buildImageDownloadName(source.name || "manual-edit", blob);
      const file = new File([blob], filename, { type: "image/png" });
      const saved = await gameKnifeApiClient.saveManualEditAsset(file, filename, source.sourceFileId, source.sourceContext);
      editorRef.current?.markSaved();
      setSaveMessage(`已保存：${saved.filename}`);
    } catch (error) {
      onFailure({
        title: "图片保存失败",
        message: "手动编辑结果没有写入资源库。",
        detail: error instanceof Error ? error.message : "保存失败。",
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="manual-editor-page">
      <input
        ref={fileInput}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        hidden
        disabled={!canWrite}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onUpload(file);
          event.currentTarget.value = "";
        }}
      />

      <ManualEditorLayout
        tools={<ManualEditorToolRail activeTool={tool} onSelect={setTool} />}
        stage={
          <ManualEditorStage
            editorRef={editorRef}
            source={source}
            tool={tool}
            brush={brush}
            gridVisible={gridVisible}
            transparentBackgroundVisible={transparentBackgroundVisible}
            exportBackgroundMode={exportBackgroundMode}
            exportBackgroundColor={exportBackgroundColor}
            magicTolerance={magicTolerance}
            magicAlphaTolerance={magicAlphaTolerance}
            magicContiguous={magicContiguous}
            zoomPreviewMode={zoomPreviewMode}
            status={status}
            canWrite={canWrite}
            saving={saving}
            onBrushChange={setBrush}
            onStatusChange={setStatus}
            onFailure={onFailure}
            onImport={importImage}
            onSave={() => void saveEditedImage()}
            onExport={() => void downloadEditedImage()}
          />
        }
        inspector={
          <ManualEditorInspector
            editorRef={editorRef}
            hasSource={Boolean(source)}
            canWrite={canWrite}
            tool={tool}
            brush={brush}
            gridVisible={gridVisible}
            transparentBackgroundVisible={transparentBackgroundVisible}
            exportBackgroundMode={exportBackgroundMode}
            exportBackgroundColor={exportBackgroundColor}
            magicTolerance={magicTolerance}
            magicAlphaTolerance={magicAlphaTolerance}
            magicContiguous={magicContiguous}
            zoomPreviewMode={zoomPreviewMode}
            alphaThreshold={alphaThreshold}
            edgeAmount={edgeAmount}
            featherRadius={featherRadius}
            padding={padding}
            status={status}
            saving={saving}
            saveMessage={saveMessage}
            onBrushChange={setBrush}
            onGridVisibleChange={onGridVisibleChange}
            onTransparentBackgroundVisibleChange={setTransparentBackgroundVisible}
            onExportBackgroundModeChange={setExportBackgroundMode}
            onExportBackgroundColorChange={setExportBackgroundColor}
            onMagicToleranceChange={setMagicTolerance}
            onMagicAlphaToleranceChange={setMagicAlphaTolerance}
            onMagicContiguousChange={setMagicContiguous}
            onZoomPreviewModeChange={setZoomPreviewMode}
            onAlphaThresholdChange={setAlphaThreshold}
            onEdgeAmountChange={setEdgeAmount}
            onFeatherRadiusChange={setFeatherRadius}
            onPaddingChange={setPadding}
            onImport={importImage}
            onDownload={() => void downloadEditedImage()}
            onSave={() => void saveEditedImage()}
          />
        }
      />
    </main>
  );
}

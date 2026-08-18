import { gameKnifeApiClient } from "@gameknife/api-client";
import React, { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
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
 * Owns cross-panel state, asset import, and save operations for manual editing. Tool navigation, canvas,
 * inspector, layers, and history stay in focused components so local input state does not accumulate here.
 */
export function ManualEditPage({
  source,
  gridVisible,
  canWrite,
  onGridVisibleChange,
  onUpload,
  onFailure,
}: {
  source: ManualEditSource | null;
  gridVisible: boolean;
  canWrite: boolean;
  onGridVisibleChange: React.Dispatch<React.SetStateAction<boolean>>;
  onUpload: (file: File) => void;
  onFailure: React.Dispatch<React.SetStateAction<FailureDialogState | null>>;
}) {
  const { t } = useTranslation("manualEditor");
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
        title: t("errors.downloadTitle"),
        message: t("errors.downloadMessage"),
        detail: error instanceof Error ? error.message : t("errors.downloadDetail"),
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
      setSaveMessage(t("status.saved", { filename: saved.filename }));
    } catch (error) {
      onFailure({
        title: t("errors.saveTitle"),
        message: t("errors.saveMessage"),
        detail: error instanceof Error ? error.message : t("errors.saveDetail"),
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="manual-editor-page">
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
            onUpload={onUpload}
            onSave={() => void saveEditedImage()}
            onExport={() => void downloadEditedImage()}
          />
        }
        inspector={
          <ManualEditorInspector
            editorRef={editorRef}
            hasSource={Boolean(source)}
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
            sourceName={source?.name}
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
          />
        }
      />
    </main>
  );
}

import type { Dispatch, RefObject, SetStateAction } from "react";
import type { EditorBrushSettings, EditorExportBackgroundMode, EditorTool, EditorZoomPreviewMode } from "@gameknife/editor-core";
import { Button, WorkbenchPreview } from "@gameknife/ui-kit";
import type { FailureDialogState, ManualEditSource } from "../../types/manualEdit";
import { EditorCanvas } from "./EditorCanvas";
import { ManualEditorCommandBar } from "./ManualEditorCommandBar";
import type { EditorStatus, ManualEditorHandle } from "./types";

export function ManualEditorStage({
  editorRef,
  source,
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
  status,
  canWrite,
  saving,
  onBrushChange,
  onStatusChange,
  onFailure,
  onImport,
  onSave,
  onExport,
}: {
  editorRef: RefObject<ManualEditorHandle | null>;
  source: ManualEditSource | null;
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
  status: EditorStatus;
  canWrite: boolean;
  saving: boolean;
  onBrushChange: Dispatch<SetStateAction<EditorBrushSettings>>;
  onStatusChange: Dispatch<SetStateAction<EditorStatus>>;
  onFailure: Dispatch<SetStateAction<FailureDialogState | null>>;
  onImport: () => void;
  onSave: () => void;
  onExport: () => void;
}) {
  return (
    <section className="manual-editor-stage">
      <ManualEditorCommandBar
        sourceName={source?.name}
        hasSource={Boolean(source)}
        status={status}
        canWrite={canWrite}
        saving={saving}
        onUndo={() => editorRef.current?.undo()}
        onRedo={() => editorRef.current?.redo()}
        onImport={onImport}
        onSave={onSave}
        onExport={onExport}
      />

      <WorkbenchPreview key={source ? `manual-edit-${source.url}` : "manual-edit-empty"} contentMode={source ? "intrinsic" : "fill"}>
        {source ? (
          <EditorCanvas
            ref={editorRef}
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
            onBrushChange={onBrushChange}
            onStatusChange={onStatusChange}
            onFailure={onFailure}
          />
        ) : (
          <div className="manual-editor-empty">
            <strong>导入一张图片</strong>
            <Button variant="primary" disabled={!canWrite} onClick={onImport}>
              选择图片
            </Button>
          </div>
        )}
      </WorkbenchPreview>
    </section>
  );
}

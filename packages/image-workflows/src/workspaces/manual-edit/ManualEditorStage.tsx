import type { Dispatch, RefObject, SetStateAction } from "react";
import type { EditorBrushSettings, EditorExportBackgroundMode, EditorTool, EditorZoomPreviewMode } from "@gameknife/editor-core";
import { WorkbenchPreview } from "@gameknife/ui-kit";
import type { FailureDialogState, ManualEditSource } from "../../types/manualEdit";
import { EditorCanvas } from "./EditorCanvas";
import { ManualEditorActionBar } from "./ManualEditorActionBar";
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
  onUpload,
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
  onUpload: (file: File) => void;
  onSave: () => void;
  onExport: () => void;
}) {
  return (
    <section className="manual-editor-stage">
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
        ) : null}
      </WorkbenchPreview>

      <ManualEditorActionBar
        hasSource={Boolean(source)}
        status={status}
        canWrite={canWrite}
        saving={saving}
        onUndo={() => editorRef.current?.undo()}
        onRedo={() => editorRef.current?.redo()}
        onUpload={onUpload}
        onSave={onSave}
        onExport={onExport}
      />
    </section>
  );
}

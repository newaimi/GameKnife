import { Button } from "@gameknife/ui-kit";
import { useTranslation } from "react-i18next";
import { ImageUploadAction, WorkbenchActionBar } from "../../components/WorkbenchActionBar";
import { readManualEditorActionState } from "./manualEditorActionState";
import type { EditorStatus } from "./types";

/**
 * Places document import, history commands, save, and export in the centered workbench toolbar.
 * The editor handle and page save flow execute commands; this component only renders explicit action state.
 */
export function ManualEditorActionBar({
  hasSource,
  status,
  canWrite,
  saving,
  onUndo,
  onRedo,
  onUpload,
  onSave,
  onExport,
}: {
  hasSource: boolean;
  status: EditorStatus;
  canWrite: boolean;
  saving: boolean;
  onUndo: () => void;
  onRedo: () => void;
  onUpload: (file: File) => void;
  onSave: () => void;
  onExport: () => void;
}) {
  const { t } = useTranslation("manualEditor");
  const actionState = readManualEditorActionState({
    hasSource,
    canWrite,
    saving,
    canUndo: status.canUndo,
    canRedo: status.canRedo,
  });

  return (
    <WorkbenchActionBar>
      <ImageUploadAction label={hasSource ? t("actions.replaceImage") : t("actions.importImage")} disabled={actionState.uploadDisabled} onFile={onUpload} />
      <Button disabled={actionState.undoDisabled} onClick={onUndo}>
        {t("actions.undo")}
      </Button>
      <Button disabled={actionState.redoDisabled} onClick={onRedo}>
        {t("actions.redo")}
      </Button>
      <Button variant="primary" disabled={actionState.saveDisabled} onClick={onSave}>
        {saving ? t("actions.saving") : t("actions.save")}
      </Button>
      <Button disabled={actionState.exportDisabled} onClick={onExport}>
        {t("actions.export")}
      </Button>
    </WorkbenchActionBar>
  );
}

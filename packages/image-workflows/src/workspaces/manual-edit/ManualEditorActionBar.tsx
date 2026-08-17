import { Button } from "@gameknife/ui-kit";
import { ImageUploadAction, WorkbenchActionBar } from "../../components/WorkbenchActionBar";
import { readManualEditorActionState } from "./manualEditorActionState";
import type { EditorStatus } from "./types";

/**
 * 手动编辑页的主操作入口。导入、历史命令、保存和下载统一放在视口底部，
 * 具体命令仍通过编辑器句柄和页面保存链路执行，布局组件不推断编辑状态。
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
  const actionState = readManualEditorActionState({
    hasSource,
    canWrite,
    saving,
    canUndo: status.canUndo,
    canRedo: status.canRedo,
  });

  return (
    <WorkbenchActionBar>
      <ImageUploadAction label={actionState.uploadLabel} disabled={actionState.uploadDisabled} onFile={onUpload} />
      <Button disabled={actionState.undoDisabled} onClick={onUndo}>
        撤销
      </Button>
      <Button disabled={actionState.redoDisabled} onClick={onRedo}>
        重做
      </Button>
      <Button variant="primary" disabled={actionState.saveDisabled} onClick={onSave}>
        {actionState.saveLabel}
      </Button>
      <Button disabled={actionState.exportDisabled} onClick={onExport}>
        导出
      </Button>
    </WorkbenchActionBar>
  );
}

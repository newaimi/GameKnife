import { Button } from "@gameknife/ui-kit";
import type { EditorStatus } from "./types";

export function ManualEditorCommandBar({
  sourceName,
  hasSource,
  status,
  canWrite,
  saving,
  onUndo,
  onRedo,
  onImport,
  onSave,
  onExport,
}: {
  sourceName?: string;
  hasSource: boolean;
  status: EditorStatus;
  canWrite: boolean;
  saving: boolean;
  onUndo: () => void;
  onRedo: () => void;
  onImport: () => void;
  onSave: () => void;
  onExport: () => void;
}) {
  return (
    <div className="manual-editor-commandbar">
      <div className="manual-editor-history-actions">
        <Button size="small" disabled={!status.canUndo} onClick={onUndo}>
          撤销
        </Button>
        <Button size="small" disabled={!status.canRedo} onClick={onRedo}>
          重做
        </Button>
      </div>
      <div className="manual-editor-status">
        <strong>{sourceName ?? "未导入图片"}</strong>
        <span>
          {status.width || "-"}×{status.height || "-"} · {status.dirty ? "未保存" : "已同步"} · {status.sample}
        </span>
      </div>
      <div className="manual-editor-export-actions">
        <Button size="small" disabled={!canWrite} onClick={onImport}>
          导入
        </Button>
        <Button size="small" disabled={!hasSource || saving || !canWrite} onClick={onSave}>
          {saving ? "保存中" : "保存"}
        </Button>
        <Button size="small" variant="primary" disabled={!hasSource} onClick={onExport}>
          导出
        </Button>
      </div>
    </div>
  );
}

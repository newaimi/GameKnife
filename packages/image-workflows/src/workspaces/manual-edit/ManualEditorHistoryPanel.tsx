import type { RefObject } from "react";
import { Button } from "@gameknife/ui-kit";
import type { EditorStatus, ManualEditorHandle } from "./types";

export function ManualEditorHistoryPanel({
  editorRef,
  status,
  hasSource,
}: {
  editorRef: RefObject<ManualEditorHandle | null>;
  status: EditorStatus;
  hasSource: boolean;
}) {
  return (
    <div className="editor-section">
      <strong>历史</strong>
      <div className="editor-action-row">
        <Button size="small" disabled={!hasSource} onClick={() => editorRef.current?.createSnapshot()}>
          保存快照
        </Button>
      </div>
      <div className="editor-history-list">
        {status.history.length ? (
          status.history.map((entry, index) => (
            <button className="editor-history-row" type="button" key={entry.id} onClick={() => editorRef.current?.jumpToHistory(index)}>
              <span>{entry.title}</span>
              <em>{new Date(entry.createdAt).toLocaleTimeString()}</em>
            </button>
          ))
        ) : (
          <p className="helper-text">暂无编辑记录。</p>
        )}
      </div>
      <div className="editor-history-list compact-list">
        {status.snapshots.map((snapshot) => (
          <button className="editor-history-row" type="button" key={snapshot.id} onClick={() => editorRef.current?.restoreSnapshot(snapshot.id)}>
            <span>{snapshot.title}</span>
            <em>快照</em>
          </button>
        ))}
      </div>
    </div>
  );
}

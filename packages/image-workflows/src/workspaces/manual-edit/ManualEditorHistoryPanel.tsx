import type { RefObject } from "react";
import { useTranslation } from "react-i18next";
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
  const { i18n, t } = useTranslation("manualEditor");
  return (
    <div className="editor-section">
      <strong>{t("history.title")}</strong>
      <div className="editor-action-row">
        <Button size="small" disabled={!hasSource} onClick={() => editorRef.current?.createSnapshot()}>
          {t("history.saveSnapshot")}
        </Button>
      </div>
      <div className="editor-history-list">
        {status.history.length ? (
          status.history.map((entry, index) => (
            <button className="editor-history-row" type="button" key={entry.id} onClick={() => editorRef.current?.jumpToHistory(index)}>
              <span>{entry.title}</span>
              <em>{new Date(entry.createdAt).toLocaleTimeString(i18n.resolvedLanguage ?? i18n.language)}</em>
            </button>
          ))
        ) : (
          <p className="helper-text">{t("history.empty")}</p>
        )}
      </div>
      <div className="editor-history-list compact-list">
        {status.snapshots.map((snapshot) => (
          <button className="editor-history-row" type="button" key={snapshot.id} onClick={() => editorRef.current?.restoreSnapshot(snapshot.id)}>
            <span>{snapshot.title}</span>
            <em>{t("history.snapshot")}</em>
          </button>
        ))}
      </div>
    </div>
  );
}

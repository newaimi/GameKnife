import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { FailureDialogState, ManualEditSource } from "../../types/manualEdit";
import { FailureDialog } from "../../components/FailureDialog";
import { useWorkflowWritePermission } from "../../hooks/useWorkflowWritePermission";
import { ManualEditPage } from "./ManualEditPage";
import { loadManualEditTransfer } from "./transfer";

export function ManualEditWorkspace() {
  const { t } = useTranslation("manualEditor");
  const sourceRef = useRef<ManualEditSource | null>(null);
  const transferLoadedRef = useRef(false);
  const [source, setSource] = useState<ManualEditSource | null>(null);
  const [gridVisible, setGridVisible] = useState(true);
  const [failureDialog, setFailureDialog] = useState<FailureDialogState | null>(null);
  const canWrite = useWorkflowWritePermission("manual-edit");

  useEffect(() => {
    const searchParams = new URLSearchParams(window.location.search);
    const transferId = searchParams.get("transfer") ?? searchParams.get("edit");
    if (!transferId || transferLoadedRef.current) {
      return;
    }

    transferLoadedRef.current = true;
    loadManualEditTransfer(transferId)
      .then((nextSource) => {
        if (nextSource) {
          replaceSource(nextSource);
        }
      })
      .catch((error) => {
        setFailureDialog({
          title: t("errors.openTitle"),
          message: t("errors.openMessage"),
          detail: error instanceof Error ? error.message : t("errors.readDetail"),
        });
      });
  }, [t]);

  useEffect(() => {
    return () => {
      releaseSource(sourceRef.current);
      sourceRef.current = null;
    };
  }, []);

  function releaseSource(sourceToRelease: ManualEditSource | null) {
    if (sourceToRelease?.revokeObjectUrl) {
      URL.revokeObjectURL(sourceToRelease.url);
    }
  }

  function replaceSource(nextSource: ManualEditSource) {
    // StrictMode runs effects twice during development. Releasing the object URL from a source effect cleanup
    // can revoke it before the editor reads it, so release only when the source changes or the page unmounts.
    releaseSource(sourceRef.current);
    sourceRef.current = nextSource;
    setSource(nextSource);
  }

  function upload(file: File) {
    if (!canWrite) {
      return;
    }
    const objectUrl = URL.createObjectURL(file);
    replaceSource({
      name: file.name,
      url: objectUrl,
      blob: file,
      sourceContext: "manual_upload",
      revokeObjectUrl: true,
    });
  }

  return (
    <>
      <ManualEditPage
        source={source}
        gridVisible={gridVisible}
        canWrite={canWrite}
        onGridVisibleChange={setGridVisible}
        onUpload={upload}
        onFailure={setFailureDialog}
      />
      {failureDialog ? <FailureDialog dialog={failureDialog} onClose={() => setFailureDialog(null)} /> : null}
    </>
  );
}

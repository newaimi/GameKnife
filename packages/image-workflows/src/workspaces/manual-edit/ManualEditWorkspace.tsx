import { useEffect, useRef, useState } from "react";
import type { FailureDialogState, ManualEditSource } from "../../types/manualEdit";
import { FailureDialog } from "../../components/FailureDialog";
import { ManualEditPage } from "./ManualEditPage";
import { loadManualEditTransfer } from "./transfer";

export function ManualEditWorkspace() {
  const fileInput = useRef<HTMLInputElement | null>(null);
  const objectUrlRef = useRef("");
  const transferLoadedRef = useRef(false);
  const [source, setSource] = useState<ManualEditSource | null>(null);
  const [gridVisible, setGridVisible] = useState(true);
  const [failureDialog, setFailureDialog] = useState<FailureDialogState | null>(null);

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
          setSource(nextSource);
        }
      })
      .catch((error) => {
        setFailureDialog({
          title: "图片打开失败",
          message: "手动编辑没有读取到临时图片。",
          detail: error instanceof Error ? error.message : "图片读取失败。",
        });
      });
  }, []);

  useEffect(() => {
    return () => {
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
      }
      if (source?.revokeObjectUrl) {
        URL.revokeObjectURL(source.url);
      }
    };
  }, [source]);

  function upload(file: File) {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
    }
    const objectUrl = URL.createObjectURL(file);
    objectUrlRef.current = objectUrl;
    setSource({
      name: file.name,
      url: objectUrl,
      sourceContext: "manual_upload",
    });
  }

  return (
    <>
      <ManualEditPage source={source} gridVisible={gridVisible} fileInput={fileInput} onGridVisibleChange={setGridVisible} onUpload={upload} onFailure={setFailureDialog} />
      {failureDialog ? <FailureDialog dialog={failureDialog} onClose={() => setFailureDialog(null)} /> : null}
    </>
  );
}

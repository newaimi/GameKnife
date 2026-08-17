import { useEffect, useRef, useState } from "react";
import type { FailureDialogState, ManualEditSource } from "../../types/manualEdit";
import { FailureDialog } from "../../components/FailureDialog";
import { useWorkflowWritePermission } from "../../hooks/useWorkflowWritePermission";
import { ManualEditPage } from "./ManualEditPage";
import { loadManualEditTransfer } from "./transfer";

export function ManualEditWorkspace() {
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
          title: "图片打开失败",
          message: "手动编辑没有读取到临时图片。",
          detail: error instanceof Error ? error.message : "图片读取失败。",
        });
      });
  }, []);

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
    // 手动编辑页会在开发模式 StrictMode 下重复执行 effect。
    // 对象 URL 如果绑在 effect 的 source 清理函数里，会在编辑器读取前被提前释放。
    // 这里把释放时机收敛到“图片被替换”和“页面卸载”，保证当前图片始终可读。
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

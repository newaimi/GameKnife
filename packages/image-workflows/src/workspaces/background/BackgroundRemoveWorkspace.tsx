import { useState } from "react";
import { gameKnifeApiClient } from "@gameknife/api-client";
import type { BackgroundRemoveParameters } from "@gameknife/shared-types";
import { NumberField, WorkbenchPreview } from "@gameknife/ui-kit";
import { ComparePreview, EmptyCanvas } from "../../components/ImageComparePreview";
import { StatusLine } from "../../components/StatusLine";
import { ToolWorkspaceLayout } from "../../components/ToolWorkspaceLayout";
import { ImageUploadStrip } from "../../components/UploadStrip";
import { WorkflowResultFooter } from "../../components/WorkflowResultFooter";
import { useImageAssetUpload } from "../../hooks/useImageAssetUpload";
import { useModelRequirement } from "../../hooks/useModelRequirement";
import { useWorkflowWritePermission } from "../../hooks/useWorkflowWritePermission";
import { useWorkflowJob } from "../../hooks/useWorkflowJob";
import { downloadOutputAsset } from "../../utils/assets";
import { JOB_POLLING_PRESETS, readFirstJobOutputAsset } from "../../utils/jobs";
import { openManualEdit } from "../../utils/manualEdit";

export function BackgroundRemoveWorkspace() {
  const [params, setParams] = useState<BackgroundRemoveParameters>({ alpha_smoothing: 0 });
  const [compare, setCompare] = useState(50);
  const { job, busy: jobBusy, error: jobError, failureDialog, setFailureDialog, runJob, resetJob } = useWorkflowJob();
  const ensureModelReady = useModelRequirement();
  const canWrite = useWorkflowWritePermission("background-remove");
  const { asset, upload, uploading, uploadError } = useImageAssetUpload({
    onBeforeUpload: () => {
      resetJob();
      setCompare(50);
    },
  });
  const busy = uploading || jobBusy;
  const error = uploadError || jobError;
  const outputAsset = job?.type === "background_remove" ? readFirstJobOutputAsset(job) : undefined;

  async function run() {
    if (!asset || !canWrite) {
      return;
    }
    if (!(await ensureModelReady("birefnet"))) {
      return;
    }
    await runJob({
      createJob: () => gameKnifeApiClient.createBackgroundRemoveJob(asset.id, params),
      failureTitle: "任务创建失败",
      failureMessage: "后端拒绝创建去背景任务，下面是接口返回的错误内容。",
      polling: JOB_POLLING_PRESETS.standard,
    });
  }

  return (
    <>
      <ImageUploadStrip
        title={asset ? "已上传图片" : "上传图片"}
        description="支持 JPG / PNG / WebP，最大 50MB"
        disabled={!canWrite}
        onFile={upload}
      />

      <ToolWorkspaceLayout activeToolId="background-remove">
        <section className="preview-stage">
          <div className="stage-toolbar">
            <div>
              <h2>AI 去背景</h2>
              <p>{asset ? `${asset.filename} · ${job?.status === "success" ? "处理完成" : "等待处理"}` : "上传图片后生成透明 PNG。"}</p>
            </div>
            <div className="toolbar-actions">
              {outputAsset ? (
                <button className="ghost" type="button" onClick={() => void downloadOutputAsset(outputAsset, `${asset?.filename ?? "background"}_cutout.png`)}>
                  下载
                </button>
              ) : null}
              <button className="primary" type="button" disabled={!asset || busy || !canWrite} onClick={() => void run()}>
                {busy ? "处理中" : "开始处理"}
              </button>
            </div>
          </div>

          <WorkbenchPreview key={`background-${asset?.id ?? "empty"}-${outputAsset?.id ?? "none"}`}>
            {!asset ? (
              <EmptyCanvas />
            ) : (
              <ComparePreview
                original={asset.url}
                result={outputAsset?.url ?? ""}
                compare={compare}
                onCompare={setCompare}
                manualEditDisabled={!canWrite}
                onManualEdit={openManualEdit}
              />
            )}
          </WorkbenchPreview>
        </section>

        <aside className="settings-panel">
          <h2>当前参数</h2>
          <NumberField
            label="Alpha 平滑"
            value={params.alpha_smoothing}
            min={0}
            max={10}
            onChange={(alpha_smoothing) => setParams((current) => ({ ...current, alpha_smoothing }))}
          />
          <div className="hint-box">
            <strong>导出说明</strong>
            <p>去背景只负责生成透明 PNG。需要换背景色时，进入手动编辑后在导出设置里合成。</p>
          </div>
          <StatusLine error={error} job={job} />
        </aside>
      </ToolWorkspaceLayout>

      <WorkflowResultFooter refreshKey={job?.id ?? asset?.id ?? ""} failureDialog={failureDialog} onCloseFailure={() => setFailureDialog(null)} />
    </>
  );
}

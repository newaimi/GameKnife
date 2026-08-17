import { useState } from "react";
import { gameKnifeApiClient } from "@gameknife/api-client";
import type { UpscaleParameters } from "@gameknife/shared-types";
import { Button, NumberField, WorkbenchPreview } from "@gameknife/ui-kit";
import { ComparePreview, EmptyCanvas } from "../../components/ImageComparePreview";
import { StatusLine } from "../../components/StatusLine";
import { ToolWorkspaceLayout } from "../../components/ToolWorkspaceLayout";
import { ImageUploadAction, WorkbenchActionBar } from "../../components/WorkbenchActionBar";
import { WorkflowFailureDialog } from "../../components/WorkflowFailureDialog";
import { useImageAssetUpload } from "../../hooks/useImageAssetUpload";
import { useModelRequirement } from "../../hooks/useModelRequirement";
import { useWorkflowJob } from "../../hooks/useWorkflowJob";
import { useWorkflowWritePermission } from "../../hooks/useWorkflowWritePermission";
import { downloadOutputAsset } from "../../utils/assets";
import { JOB_POLLING_PRESETS, readFirstJobOutputAsset } from "../../utils/jobs";
import { openManualEdit } from "../../utils/manualEdit";

const UPSCALE_STYLE_OPTIONS: Array<{ value: UpscaleParameters["style"]; label: string; note: string }> = [
  { value: "general", label: "通用素材", note: "角色、道具、UI" },
  { value: "anime", label: "动漫插画", note: "线稿和卡通" },
  { value: "noisy", label: "噪点压缩", note: "低清和 JPEG" },
  { value: "pixel", label: "像素风", note: "最近邻硬边" },
];

const DEFAULT_UPSCALE_PARAMS: UpscaleParameters = {
  style: "general",
  scale: 4,
  denoise: 1,
  tile_size: 384,
};

export function UpscaleWorkspace() {
  const [params, setParams] = useState<UpscaleParameters>(DEFAULT_UPSCALE_PARAMS);
  const [compare, setCompare] = useState(50);
  const { job, busy: jobBusy, error: jobError, failureDialog, setFailureDialog, runJob, resetJob } = useWorkflowJob();
  const ensureModelReady = useModelRequirement();
  const canWrite = useWorkflowWritePermission("upscale");
  const { asset, upload, uploading, uploadError } = useImageAssetUpload({
    onBeforeUpload: () => {
      resetJob();
      setCompare(50);
    },
  });
  const busy = uploading || jobBusy;
  const error = uploadError || jobError;
  const outputAsset = job?.type === "image_upscale" ? readFirstJobOutputAsset(job) : undefined;
  const warnings = Array.isArray(job?.result.warnings) ? job.result.warnings.map(String) : [];

  async function run() {
    if (!asset || !canWrite) {
      return;
    }
    if (params.style !== "pixel" && !(await ensureModelReady("upscale"))) {
      return;
    }
    await runJob({
      createJob: () => gameKnifeApiClient.createUpscaleJob(asset.id, params),
      failureTitle: "任务创建失败",
      failureMessage: "后端拒绝创建图片放大任务，下面是接口返回的错误内容。",
      polling: JOB_POLLING_PRESETS.long,
    });
  }

  return (
    <>
      <ToolWorkspaceLayout activeToolId="upscale">
        <section className="preview-stage upscale-stage">
          <WorkbenchPreview key={`upscale-${asset?.id ?? "empty"}-${outputAsset?.id ?? "none"}`}>
            {!asset ? (
              <EmptyCanvas />
            ) : (
              <ComparePreview
                original={asset.url}
                result={outputAsset?.url ?? ""}
                compare={compare}
                previewTitle="图片放大结果"
                previewDescription="双击打开的超分放大结果。"
                manualEditName={`${asset.filename.replace(/\.[^.]+$/, "")}_upscale.png`}
                manualEditContext="image_upscale"
                onCompare={setCompare}
                manualEditDisabled={!canWrite}
                onManualEdit={openManualEdit}
              />
            )}
          </WorkbenchPreview>
        </section>

        <aside className="settings-panel upscale-settings">
          <h2>放大参数</h2>
          <div className="upscale-style-grid" aria-label="图片风格">
            {UPSCALE_STYLE_OPTIONS.map((option) => (
              <button
                key={option.value}
                className={params.style === option.value ? "active" : ""}
                type="button"
                onClick={() => setParams((current) => ({ ...current, style: option.value }))}
              >
                <strong>{option.label}</strong>
                <span>{option.note}</span>
              </button>
            ))}
          </div>
          <label className="number-field">
            <span>放大倍率</span>
            <select value={params.scale} onChange={(event) => setParams((current) => ({ ...current, scale: Number(event.target.value) as UpscaleParameters["scale"] }))}>
              <option value={2}>2x</option>
              <option value={4}>4x</option>
              <option value={8}>8x</option>
            </select>
          </label>
          <label className="number-field">
            <span>降噪强度</span>
            <select
              value={params.denoise}
              disabled={params.style === "pixel"}
              onChange={(event) => setParams((current) => ({ ...current, denoise: Number(event.target.value) }))}
            >
              <option value={0}>关闭</option>
              <option value={1}>轻度</option>
              <option value={2}>中度</option>
              <option value={3}>强度</option>
            </select>
          </label>
          <NumberField label="Tile Size" value={params.tile_size} min={128} max={1024} onChange={(tile_size) => setParams((current) => ({ ...current, tile_size }))} />
          {warnings.length ? (
            <div className="hint-box warning">
              <strong>注意</strong>
              <p>{warnings.join(" ")}</p>
            </div>
          ) : null}
          <div className="export-stack">
            <Button
              variant="secondary"
              disabled={!outputAsset || !canWrite}
              onClick={() =>
                outputAsset
                  ? void openManualEdit({
                      name: `${asset?.filename ?? "upscale"}_upscale.png`,
                      url: outputAsset.url,
                      sourceFileId: outputAsset.id,
                      sourceContext: "image_upscale",
                    })
                  : undefined
              }
            >
              手动编辑
            </Button>
          </div>
          <StatusLine error={error} job={job} />
        </aside>

        <WorkbenchActionBar>
          <ImageUploadAction label={asset ? "更换图片" : "上传图片"} disabled={!canWrite} onFile={upload} />
          <Button variant="primary" disabled={!asset || busy || !canWrite} onClick={() => void run()}>
            {busy ? "处理中" : "开始放大"}
          </Button>
          <Button
            variant="secondary"
            disabled={!outputAsset}
            onClick={() => (outputAsset ? void downloadOutputAsset(outputAsset, `${asset?.filename ?? "upscale"}_upscale.png`) : undefined)}
          >
            下载
          </Button>
        </WorkbenchActionBar>
      </ToolWorkspaceLayout>

      <WorkflowFailureDialog failureDialog={failureDialog} onCloseFailure={() => setFailureDialog(null)} />
    </>
  );
}

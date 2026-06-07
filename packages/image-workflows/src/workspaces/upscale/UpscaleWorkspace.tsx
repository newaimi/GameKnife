import { useState } from "react";
import { gameKnifeApiClient } from "@gameknife/api-client";
import type { UpscaleParameters } from "@gameknife/shared-types";
import { NumberField, WorkbenchPreview } from "@gameknife/ui-kit";
import { ComparePreview, EmptyCanvas } from "../../components/ImageComparePreview";
import { StatusLine } from "../../components/JobResult";
import { ToolWorkspaceLayout } from "../../components/ToolWorkspaceLayout";
import { ImageUploadStrip } from "../../components/UploadStrip";
import { WorkflowResultFooter } from "../../components/WorkflowResultFooter";
import { useImageAssetUpload } from "../../hooks/useImageAssetUpload";
import { useModelRequirement } from "../../hooks/useModelRequirement";
import { useWorkflowDevice } from "../../hooks/useWorkflowDevice";
import { useWorkflowJob } from "../../hooks/useWorkflowJob";
import { useWorkflowWritePermission } from "../../hooks/useWorkflowWritePermission";
import { downloadOutputAsset } from "../../utils/assets";
import { formatImageSize } from "../../utils/formatters";
import { JOB_POLLING_PRESETS, readFirstJobOutputAsset, readTupleNumber } from "../../utils/jobs";
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
  const device = useWorkflowDevice("upscale");
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
  const selectedStyle = UPSCALE_STYLE_OPTIONS.find((option) => option.value === params.style) ?? UPSCALE_STYLE_OPTIONS[0];
  const outputSize = readTupleNumber(job?.result.output_size);
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
      <ImageUploadStrip
        title={asset ? "已导入待放大图片" : "导入待放大图片"}
        description="支持 PNG / JPG / WebP，输出默认保留透明通道"
        disabled={!canWrite}
        onFile={upload}
      />

      <ToolWorkspaceLayout activeToolId="upscale">
        <section className="preview-stage upscale-stage">
          <div className="stage-toolbar">
            <div>
              <h2>图片放大</h2>
              <p>{asset ? `${selectedStyle.label} · ${params.scale}x · ${formatImageSize(outputSize)}` : "导入图片后按素材风格选择放大方式。"}</p>
            </div>
            <div className="toolbar-actions">
              <span className="device-pill">{device}</span>
              {outputAsset ? (
                <button className="ghost" type="button" onClick={() => void downloadOutputAsset(outputAsset, `${asset?.filename ?? "upscale"}_upscale.png`)}>
                  下载
                </button>
              ) : null}
              {outputAsset ? (
                <button
                  className="ghost"
                  type="button"
                  disabled={!canWrite}
                  onClick={() =>
                    void openManualEdit({
                      name: `${asset?.filename ?? "upscale"}_upscale.png`,
                      url: outputAsset.url,
                      sourceFileId: outputAsset.id,
                      sourceContext: "image_upscale",
                    })
                  }
                >
                  手动编辑
                </button>
              ) : null}
              <button className="primary" type="button" disabled={!asset || busy || !canWrite} onClick={() => void run()}>
                {busy ? "处理中" : "开始放大"}
              </button>
            </div>
          </div>

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
          <div className="hint-box">
            <strong>处理策略</strong>
            <p>像素风直接最近邻放大。其他风格需要先在设置页安装 Real-ESRGAN 模型文件。</p>
          </div>
          {warnings.length ? (
            <div className="hint-box warning">
              <strong>注意</strong>
              <p>{warnings.join(" ")}</p>
            </div>
          ) : null}
          <StatusLine error={error} job={job} />
        </aside>
      </ToolWorkspaceLayout>

      <WorkflowResultFooter job={job} refreshKey={job?.id ?? asset?.id ?? ""} failureDialog={failureDialog} onCloseFailure={() => setFailureDialog(null)} />
    </>
  );
}

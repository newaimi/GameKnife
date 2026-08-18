import { useState } from "react";
import { useTranslation } from "react-i18next";
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

const UPSCALE_STYLE_OPTIONS: UpscaleParameters["style"][] = ["general", "anime", "noisy", "pixel"];

const DEFAULT_UPSCALE_PARAMS: UpscaleParameters = {
  style: "general",
  scale: 4,
  denoise: 1,
  tile_size: 384,
};

export function UpscaleWorkspace() {
  const { t } = useTranslation("workflows");
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
      failureTitle: t("common.jobCreationFailed"),
      failureMessage: t("common.backendRejected", { workflow: t("upscale.workflow") }),
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
                previewTitle={t("upscale.resultTitle")}
                previewDescription={t("upscale.resultDescription")}
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
          <h2>{t("upscale.parameters")}</h2>
          <div className="upscale-style-grid" aria-label={t("upscale.styleLabel")}>
            {UPSCALE_STYLE_OPTIONS.map((option) => (
              <button
                key={option}
                className={params.style === option ? "active" : ""}
                type="button"
                onClick={() => setParams((current) => ({ ...current, style: option }))}
              >
                <strong>{t(`upscale.styles.${option}.label`)}</strong>
                <span>{t(`upscale.styles.${option}.note`)}</span>
              </button>
            ))}
          </div>
          <label className="number-field">
            <span>{t("upscale.scale")}</span>
            <select value={params.scale} onChange={(event) => setParams((current) => ({ ...current, scale: Number(event.target.value) as UpscaleParameters["scale"] }))}>
              <option value={2}>2x</option>
              <option value={4}>4x</option>
              <option value={8}>8x</option>
            </select>
          </label>
          <label className="number-field">
            <span>{t("upscale.denoise")}</span>
            <select
              value={params.denoise}
              disabled={params.style === "pixel"}
              onChange={(event) => setParams((current) => ({ ...current, denoise: Number(event.target.value) }))}
            >
              <option value={0}>{t("upscale.denoiseOff")}</option>
              <option value={1}>{t("upscale.denoiseLight")}</option>
              <option value={2}>{t("upscale.denoiseMedium")}</option>
              <option value={3}>{t("upscale.denoiseStrong")}</option>
            </select>
          </label>
          <NumberField label={t("upscale.tileSize")} value={params.tile_size} min={128} max={1024} onChange={(tile_size) => setParams((current) => ({ ...current, tile_size }))} />
          {warnings.length ? (
            <div className="hint-box warning">
              <strong>{t("upscale.warning")}</strong>
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
              {t("upscale.manualEdit")}
            </Button>
          </div>
          <StatusLine error={error} job={job} />
        </aside>

        <WorkbenchActionBar>
          <ImageUploadAction label={asset ? t("common.replaceImage") : t("common.uploadImage")} disabled={!canWrite} onFile={upload} />
          <Button variant="primary" disabled={!asset || busy || !canWrite} onClick={() => void run()}>
            {busy ? t("common.processing") : t("upscale.start")}
          </Button>
          <Button
            variant="secondary"
            disabled={!outputAsset}
            onClick={() => (outputAsset ? void downloadOutputAsset(outputAsset, `${asset?.filename ?? "upscale"}_upscale.png`) : undefined)}
          >
            {t("common.download")}
          </Button>
        </WorkbenchActionBar>
      </ToolWorkspaceLayout>

      <WorkflowFailureDialog failureDialog={failureDialog} onCloseFailure={() => setFailureDialog(null)} />
    </>
  );
}

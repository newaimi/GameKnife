import { useState } from "react";
import { useTranslation } from "react-i18next";
import { gameKnifeApiClient } from "@gameknife/api-client";
import type { BackgroundRemoveParameters } from "@gameknife/shared-types";
import { Button, NumberField, WorkbenchPreview } from "@gameknife/ui-kit";
import { ComparePreview, EmptyCanvas } from "../../components/ImageComparePreview";
import { StatusLine } from "../../components/StatusLine";
import { ToolWorkspaceLayout } from "../../components/ToolWorkspaceLayout";
import { ImageUploadAction, WorkbenchActionBar } from "../../components/WorkbenchActionBar";
import { WorkflowFailureDialog } from "../../components/WorkflowFailureDialog";
import { useImageAssetUpload } from "../../hooks/useImageAssetUpload";
import { useModelRequirement } from "../../hooks/useModelRequirement";
import { useWorkflowWritePermission } from "../../hooks/useWorkflowWritePermission";
import { useWorkflowJob } from "../../hooks/useWorkflowJob";
import { downloadOutputAsset } from "../../utils/assets";
import { JOB_POLLING_PRESETS, readFirstJobOutputAsset } from "../../utils/jobs";
import { openManualEdit } from "../../utils/manualEdit";

export function BackgroundRemoveWorkspace() {
  const { t } = useTranslation("workflows");
  const { t: tWorkbench } = useTranslation("workbench");
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
      failureTitle: t("common.jobCreationFailed"),
      failureMessage: t("common.backendRejected", { workflow: t("background.workflow") }),
      polling: JOB_POLLING_PRESETS.standard,
    });
  }

  return (
    <>
      <ToolWorkspaceLayout activeToolId="background-remove">
        <section className="preview-stage">
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
          <h2>{tWorkbench("parameters")}</h2>
          <NumberField
            label={t("background.alphaSmoothing")}
            value={params.alpha_smoothing}
            min={0}
            max={10}
            onChange={(alpha_smoothing) => setParams((current) => ({ ...current, alpha_smoothing }))}
          />
          <StatusLine error={error} job={job} />
        </aside>

        <WorkbenchActionBar>
          <ImageUploadAction label={asset ? t("common.replaceImage") : t("common.uploadImage")} disabled={!canWrite} onFile={upload} />
          <Button variant="primary" disabled={!asset || busy || !canWrite} onClick={() => void run()}>
            {busy ? t("common.processing") : t("common.process")}
          </Button>
          <Button
            variant="secondary"
            disabled={!outputAsset}
            onClick={() => (outputAsset ? void downloadOutputAsset(outputAsset, `${asset?.filename ?? "background"}_cutout.png`) : undefined)}
          >
            {t("common.download")}
          </Button>
        </WorkbenchActionBar>
      </ToolWorkspaceLayout>

      <WorkflowFailureDialog failureDialog={failureDialog} onCloseFailure={() => setFailureDialog(null)} />
    </>
  );
}

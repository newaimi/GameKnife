import { useState } from "react";
import { useTranslation } from "react-i18next";
import { gameKnifeApiClient } from "@gameknife/api-client";
import type { JobResponse, OutputAssetRef, VideoSequenceGenerateParameters } from "@gameknife/shared-types";
import { ToolWorkspaceLayout } from "../../components/ToolWorkspaceLayout";
import { ImageUploadAction } from "../../components/WorkbenchActionBar";
import { WorkflowFailureDialog } from "../../components/WorkflowFailureDialog";
import { useImageAssetUpload } from "../../hooks/useImageAssetUpload";
import { useWorkflowJob } from "../../hooks/useWorkflowJob";
import { useWorkflowWritePermission } from "../../hooks/useWorkflowWritePermission";
import { JOB_POLLING_PRESETS, readFirstJobOutputAsset } from "../../utils/jobs";
import { openManualEdit } from "../../utils/manualEdit";
import { VideoGenerateEditor } from "../sequence/VideoSequenceEditors";
import { saveVideoToSequenceTransfer } from "../sequence/videoToSequenceTransfer";

const DEFAULT_VIDEO_PARAMS: VideoSequenceGenerateParameters = {
  action: "walk_down",
  prompt: "",
  negative_prompt: "",
  duration: 5,
  resolution: "720P",
};

type VideoJobResponse = JobResponse & {
  result: JobResponse["result"] & {
    video_url?: string;
    video_filename?: string;
    video_size_bytes?: number;
  };
};

export function VideoGenerateWorkspace() {
  const { t } = useTranslation("workflows");
  const [params, setParams] = useState<VideoSequenceGenerateParameters>(DEFAULT_VIDEO_PARAMS);
  const { job, busy: jobBusy, error: jobError, failureDialog, setFailureDialog, runJob, resetJob } = useWorkflowJob<VideoJobResponse>();
  const canWrite = useWorkflowWritePermission("video-generate");
  const { asset, upload, uploading, uploadError } = useImageAssetUpload({ onBeforeUpload: resetJob });
  const busy = uploading || jobBusy;
  const error = uploadError || jobError;

  async function run() {
    if (!asset || !canWrite) {
      return;
    }
    await runJob({
      createJob: () =>
        gameKnifeApiClient.createVideoGenerationJob({
          input_asset_id: asset.id,
          action: params.action,
          prompt: params.prompt,
          negative_prompt: params.negative_prompt,
          duration: params.duration,
          resolution: params.resolution,
          confirmed_external_api: true,
        }),
      failureTitle: t("common.jobCreationFailed"),
      failureMessage: t("common.backendRejected", { workflow: t("video.generationWorkflow") }),
      polling: JOB_POLLING_PRESETS.long,
      mapJob: toVideoJob,
    });
  }

  function useGeneratedVideo() {
    const outputAsset = readFirstJobOutputAsset(job);
    if (!outputAsset) {
      return;
    }
    saveVideoToSequenceTransfer({
      asset: {
        id: outputAsset.id,
        filename: job?.result.video_filename || "generated-video.mp4",
        mime_type: "video/mp4",
        size_bytes: job?.result.video_size_bytes ?? 0,
        url: outputAsset.url,
      },
      action: params.action,
    });
    window.location.href = "/tools/video-to-sequence";
  }

  return (
    <>
      <ToolWorkspaceLayout activeToolId="video-generate">
        <VideoGenerateEditor
          upload={asset}
          videoTask={job}
          params={params}
          error={error}
          canWrite={canWrite}
          isTaskProcessing={busy}
          onParamsChange={setParams}
          onStartProcess={run}
          onUseGeneratedVideo={useGeneratedVideo}
          onManualEdit={openManualEdit}
          uploadAction={<ImageUploadAction label={asset ? t("common.replaceImage") : t("common.uploadImage")} disabled={!canWrite} onFile={upload} />}
        />
      </ToolWorkspaceLayout>
      <WorkflowFailureDialog failureDialog={failureDialog} onCloseFailure={() => setFailureDialog(null)} />
    </>
  );
}

function toVideoJob(job: JobResponse): VideoJobResponse {
  const outputAsset = readFirstJobOutputAsset(job) as OutputAssetRef | undefined;
  return {
    ...job,
    result: {
      ...job.result,
      video_url: typeof job.result.video_url === "string" ? job.result.video_url : outputAsset?.url,
      video_filename: typeof job.result.video_filename === "string" ? job.result.video_filename : "generated-video.mp4",
      video_size_bytes: typeof job.result.video_size_bytes === "number" ? job.result.video_size_bytes : 0,
    },
  };
}

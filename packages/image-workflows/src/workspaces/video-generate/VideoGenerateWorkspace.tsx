import { useState } from "react";
import { gameKnifeApiClient } from "@gameknife/api-client";
import type { JobResponse, OutputAssetRef, VideoSequenceGenerateParameters } from "@gameknife/shared-types";
import { ToolWorkspaceLayout } from "../../components/ToolWorkspaceLayout";
import { ImageUploadStrip } from "../../components/UploadStrip";
import { WorkflowResultFooter } from "../../components/WorkflowResultFooter";
import { useImageAssetUpload } from "../../hooks/useImageAssetUpload";
import { useWorkflowDevice } from "../../hooks/useWorkflowDevice";
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
  const [params, setParams] = useState<VideoSequenceGenerateParameters>(DEFAULT_VIDEO_PARAMS);
  const { job, busy: jobBusy, error: jobError, failureDialog, setFailureDialog, runJob, resetJob } = useWorkflowJob<VideoJobResponse>();
  const device = useWorkflowDevice("video-generation");
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
      failureTitle: "任务创建失败",
      failureMessage: "后端拒绝创建视频生成任务，下面是接口返回的错误内容。",
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
      <ImageUploadStrip
        title={asset ? "已导入角色图" : "上传角色图"}
        description="支持 PNG / JPG / WebP，调用外部 API 生成动作视频"
        disabled={!canWrite}
        onFile={upload}
      />
      <ToolWorkspaceLayout activeToolId="video-generate">
        <VideoGenerateEditor
          upload={asset}
          currentTask={job}
          videoTask={job}
          params={params}
          device={device}
          canWrite={canWrite}
          isTaskProcessing={busy}
          onParamsChange={setParams}
          onStartProcess={run}
          onUseGeneratedVideo={useGeneratedVideo}
          onManualEdit={openManualEdit}
        />
      </ToolWorkspaceLayout>
      {error ? <p className="error-text">{error}</p> : null}
      <WorkflowResultFooter refreshKey={job?.id ?? asset?.id ?? ""} failureDialog={failureDialog} onCloseFailure={() => setFailureDialog(null)} />
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

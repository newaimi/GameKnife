import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { gameKnifeApiClient } from "@gameknife/api-client";
import type { JobResponse, SequenceResponse, VideoToSequenceParameters } from "@gameknife/shared-types";
import { ToolWorkspaceLayout } from "../../components/ToolWorkspaceLayout";
import { VideoUploadAction } from "../../components/WorkbenchActionBar";
import { WorkflowFailureDialog } from "../../components/WorkflowFailureDialog";
import { useAssetUpload } from "../../hooks/useAssetUpload";
import { useModelRequirement } from "../../hooks/useModelRequirement";
import { useWorkflowJob } from "../../hooks/useWorkflowJob";
import { useWorkflowWritePermission } from "../../hooks/useWorkflowWritePermission";
import { JOB_POLLING_PRESETS, readString } from "../../utils/jobs";
import { VideoToSequenceEditor } from "../sequence/VideoSequenceEditors";
import { consumeVideoToSequenceTransfer } from "../sequence/videoToSequenceTransfer";

const DEFAULT_VIDEO_TO_SEQUENCE_PARAMS: VideoToSequenceParameters = {
  action: "walk_down",
  clip_start_seconds: 0,
  clip_end_seconds: 2,
  fps: 12,
  output_size: 256,
  loop: true,
  alpha_smoothing: 0,
  stabilize: true,
};

type VideoJobResponse = JobResponse & {
  result: JobResponse["result"] & {
    sequence_id?: string;
  };
};

export function VideoToSequenceWorkspace() {
  const navigate = useNavigate();
  const [sequence, setSequence] = useState<SequenceResponse | null>(null);
  const [params, setParams] = useState<VideoToSequenceParameters>(DEFAULT_VIDEO_TO_SEQUENCE_PARAMS);
  const { job, busy: jobBusy, error: jobError, setError, failureDialog, setFailureDialog, runJob, resetJob } = useWorkflowJob<VideoJobResponse>();
  const ensureModelReady = useModelRequirement();
  const canWrite = useWorkflowWritePermission("video-to-sequence");
  const {
    asset: video,
    setAsset: setVideo,
    upload,
    uploading,
    uploadError,
  } = useAssetUpload({
    uploadAsset: (file) => gameKnifeApiClient.uploadVideo(file),
    onBeforeUpload: () => {
      resetJob();
      setSequence(null);
    },
  });
  const busy = uploading || jobBusy;
  const error = uploadError || jobError;

  useEffect(() => {
    try {
      const transfer = consumeVideoToSequenceTransfer();
      if (transfer) {
        setVideo(transfer.asset);
        setParams((current) => ({ ...current, action: transfer.action }));
      }
    } catch {
      setError("读取生成视频失败。");
    }
  }, []);

  async function createSequence() {
    if (!video || !canWrite) {
      return;
    }
    if (!(await ensureModelReady("birefnet"))) {
      return;
    }
    const duration = Math.max(0.1, params.clip_end_seconds - params.clip_start_seconds);
    const requestPayload = {
      video_asset_id: video.id,
      name: video.filename.replace(/\.[^.]+$/, "") || "video-sequence",
      fps: params.fps,
      max_frames: Math.max(1, Math.round(duration * params.fps)),
      start_second: params.clip_start_seconds,
      duration_seconds: duration,
      remove_background: true,
      parameters: {
        action: params.action,
        output_size: params.output_size,
        loop: params.loop,
        alpha_smoothing: params.alpha_smoothing,
        stabilize: params.stabilize,
      },
    };
    const jobParameters = {
      ...requestPayload.parameters,
      name: requestPayload.name,
      fps: requestPayload.fps,
      max_frames: requestPayload.max_frames,
      start_second: requestPayload.start_second,
      duration_seconds: requestPayload.duration_seconds,
      remove_background: requestPayload.remove_background,
    };
    const finished = await runJob({
      jobType: "sequence_video_to_frames",
      parameters: jobParameters,
      idempotencyPayload: requestPayload,
      createJob: (submission) => gameKnifeApiClient.createSequenceFromVideoJob(requestPayload, submission),
      failureTitle: "任务创建失败",
      failureMessage: "后端拒绝创建视频转帧任务，下面是接口返回的错误内容。",
      polling: JOB_POLLING_PRESETS.long,
      mapJob: toVideoJob,
    });
    const sequenceId = readString(finished?.result.sequence_id);
    if (finished?.status === "success" && sequenceId) {
      setSequence(await gameKnifeApiClient.getSequence(sequenceId));
    }
  }

  return (
    <>
      <ToolWorkspaceLayout activeToolId="video-to-sequence">
        <VideoToSequenceEditor
          video={video}
          sequence={sequence}
          currentTask={job}
          params={params}
          error={error}
          canWrite={canWrite}
          isTaskProcessing={busy}
          onParamsChange={setParams}
          onCreateSequence={createSequence}
          onOpenSequence={() => {
            navigate(sequence ? `/tools/sequence?sequence=${encodeURIComponent(sequence.id)}` : "/tools/sequence");
          }}
          uploadAction={<VideoUploadAction label={video ? "更换视频" : "上传视频"} disabled={!canWrite} onFile={upload} />}
        />
      </ToolWorkspaceLayout>
      <WorkflowFailureDialog failureDialog={failureDialog} onCloseFailure={() => setFailureDialog(null)} />
    </>
  );
}

function toVideoJob(job: JobResponse): VideoJobResponse {
  return {
    ...job,
    result: {
      ...job.result,
      sequence_id: typeof job.result.sequence_id === "string" ? job.result.sequence_id : undefined,
    },
  };
}

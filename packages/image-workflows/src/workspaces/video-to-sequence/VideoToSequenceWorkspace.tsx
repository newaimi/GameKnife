import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { gameKnifeApiClient } from "@gameknife/api-client";
import type { JobResponse, OutputAssetRef, SequenceResponse, VideoToSequenceParameters } from "@gameknife/shared-types";
import { ToolWorkspaceLayout } from "../../components/ToolWorkspaceLayout";
import { VideoUploadStrip } from "../../components/UploadStrip";
import { WorkflowResultFooter } from "../../components/WorkflowResultFooter";
import { useAssetUpload } from "../../hooks/useAssetUpload";
import { useModelRequirement } from "../../hooks/useModelRequirement";
import { useWorkflowDevice } from "../../hooks/useWorkflowDevice";
import { useWorkflowJob } from "../../hooks/useWorkflowJob";
import { readString } from "../../utils/jobs";
import { VideoToSequenceEditor } from "../sequence/VideoSequenceEditors";

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
  const device = useWorkflowDevice("birefnet");
  const ensureModelReady = useModelRequirement();
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
    const raw = window.sessionStorage.getItem("gameknife-video-to-sequence-asset");
    if (!raw) {
      return;
    }
    window.sessionStorage.removeItem("gameknife-video-to-sequence-asset");
    try {
      const asset = JSON.parse(raw) as OutputAssetRef;
      if (asset?.id && asset.url) {
        setVideo({
          id: asset.id,
          filename: "generated-video.mp4",
          mime_type: "video/mp4",
          size_bytes: 0,
          url: asset.url,
        });
      }
    } catch {
      setError("读取生成视频失败。");
    }
  }, []);

  async function createSequence() {
    if (!video) {
      return;
    }
    if (!(await ensureModelReady("birefnet"))) {
      return;
    }
    const duration = Math.max(0.1, params.clip_end_seconds - params.clip_start_seconds);
    const finished = await runJob({
      createJob: () =>
        gameKnifeApiClient.createSequenceFromVideoJob({
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
        }),
      failureTitle: "任务创建失败",
      failureMessage: "后端拒绝创建视频转帧任务，下面是接口返回的错误内容。",
      maxTries: 120,
      intervalMs: 1000,
      mapJob: toVideoJob,
    });
    const sequenceId = readString(finished?.result.sequence_id);
    if (finished?.status === "success" && sequenceId) {
      setSequence(await gameKnifeApiClient.getSequence(sequenceId));
    }
  }

  return (
    <>
      <VideoUploadStrip
        title={video ? "已导入视频" : "导入视频"}
        description="支持 MP4 / WebM / MOV，本地抽帧并转成透明序列帧"
        onFile={upload}
      />
      <ToolWorkspaceLayout activeToolId="video-to-sequence">
        <VideoToSequenceEditor
          video={video}
          sequence={sequence}
          currentTask={job}
          params={params}
          device={device}
          isTaskProcessing={busy}
          onParamsChange={setParams}
          onCreateSequence={createSequence}
          onOpenSequence={() => {
            navigate(sequence ? `/tools/sequence?sequence=${encodeURIComponent(sequence.id)}` : "/tools/sequence");
          }}
        />
      </ToolWorkspaceLayout>
      {error ? <p className="error-text">{error}</p> : null}
      <WorkflowResultFooter job={job} refreshKey={job?.id ?? video?.id ?? sequence?.id ?? ""} failureDialog={failureDialog} onCloseFailure={() => setFailureDialog(null)} />
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

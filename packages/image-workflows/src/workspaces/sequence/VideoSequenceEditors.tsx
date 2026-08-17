import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Play, Sparkles } from "lucide-react";
import type { AssetResponse, JobResponse, SequenceResponse, VideoSequenceGenerateParameters, VideoToSequenceParameters } from "@gameknife/shared-types";
import { NumberField, WorkbenchPreview } from "@gameknife/ui-kit";
import { useObjectUrl } from "../../utils/objectUrl";
import { EmptyCanvas } from "../../components/ImageComparePreview";
import { WorkbenchActionBar } from "../../components/WorkbenchActionBar";
import type { ManualEditSource } from "../../types/manualEdit";

type VideoJobResponse = JobResponse & {
  result: JobResponse["result"] & {
    video_url?: string;
    video_filename?: string;
    sequence_id?: string;
  };
};

const ACTION_OPTIONS = [
  { value: "idle", label: "待机" },
  { value: "walk_down", label: "向下走" },
  { value: "walk_up", label: "向上走" },
  { value: "walk_left", label: "向左走" },
  { value: "walk_right", label: "向右走" },
  { value: "hurt", label: "受击" },
  { value: "death", label: "死亡" },
];

export function VideoGenerateEditor({
  upload,
  videoTask,
  params,
  error,
  canWrite,
  isTaskProcessing,
  onParamsChange,
  onStartProcess,
  onUseGeneratedVideo,
  onManualEdit,
  uploadAction,
}: {
  upload: AssetResponse | null;
  videoTask: VideoJobResponse | null;
  params: VideoSequenceGenerateParameters;
  error: string;
  canWrite: boolean;
  isTaskProcessing: boolean;
  onParamsChange: React.Dispatch<React.SetStateAction<VideoSequenceGenerateParameters>>;
  onStartProcess: () => void | Promise<void>;
  onUseGeneratedVideo: () => void;
  onManualEdit: (source: Pick<ManualEditSource, "name" | "url" | "sourceFileId" | "sourceContext">) => void | Promise<void>;
  uploadAction: React.ReactNode;
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const sourceUrl = useObjectUrl(upload?.url ?? "");
  const videoUrl = useObjectUrl(videoTask?.type === "sequence_generate_video" ? videoTask.result.video_url ?? "" : "");
  const videoTaskRunning = videoTask?.type === "sequence_generate_video" && ["pending", "running"].includes(videoTask.status);
  const videoReady = Boolean(videoUrl && videoTask?.status === "success");

  function confirmApiCall() {
    if (!canWrite) {
      return;
    }
    setConfirmOpen(false);
    void onStartProcess();
  }

  return (
    <>
      <section className="preview-stage sequence-stage">
        <WorkbenchPreview key={`video-generate-${upload?.id ?? "empty"}-${videoTask?.id ?? "none"}`}>
          {!upload ? (
            <EmptyCanvas />
          ) : (
            <div className="video-tool-canvas">
              {videoUrl ? (
                <video className="video-tool-preview" src={videoUrl} controls playsInline />
              ) : sourceUrl ? (
                <img className="video-tool-source" src={sourceUrl} alt={upload.filename} />
              ) : (
                <span>正在加载图片...</span>
              )}
              {videoTaskRunning ? (
                <div className="video-tool-working">
                  <Sparkles size={22} />
                  <strong>正在调用外部视频 API</strong>
                </div>
              ) : null}
            </div>
          )}
        </WorkbenchPreview>
      </section>

      <aside className="settings-panel sequence-settings">
        <VideoGenerationPanel params={params} onParamsChange={onParamsChange} />
        <div className="export-stack">
          <button className="ghost" type="button" disabled={!sourceUrl || !upload || !canWrite} onClick={() => upload && sourceUrl ? void onManualEdit({ name: upload.filename, url: sourceUrl, sourceFileId: upload.id, sourceContext: "upload" }) : undefined}>
            编辑原图
          </button>
        </div>
        {error ? <p className="error-text">{error}</p> : null}
      </aside>

      <WorkbenchActionBar>
        {uploadAction}
        <button className="primary" type="button" disabled={!upload || isTaskProcessing || !canWrite} onClick={() => setConfirmOpen(true)}>
          {videoTaskRunning ? "生成中" : "生成视频"}
        </button>
        <a
          className={`ghost ${videoReady ? "" : "disabled"}`}
          href={videoReady ? videoUrl : undefined}
          download={videoTask?.result.video_filename || "generated-video.mp4"}
          aria-disabled={!videoReady}
          onClick={(event) => {
            if (!videoReady) event.preventDefault();
          }}
        >
          下载
        </a>
        <button className="ghost" type="button" disabled={!videoReady || !canWrite} onClick={onUseGeneratedVideo}>
          发送到视频转帧
        </button>
      </WorkbenchActionBar>

      {confirmOpen ? <VideoApiConfirmDialog onCancel={() => setConfirmOpen(false)} onConfirm={confirmApiCall} /> : null}
    </>
  );
}

export function VideoToSequenceEditor({
  video,
  sequence,
  currentTask,
  params,
  error,
  canWrite,
  isTaskProcessing,
  onParamsChange,
  onCreateSequence,
  onOpenSequence,
  uploadAction,
}: {
  video: AssetResponse | null;
  sequence: SequenceResponse | null;
  currentTask: VideoJobResponse | null;
  params: VideoToSequenceParameters;
  error: string;
  canWrite: boolean;
  isTaskProcessing: boolean;
  onParamsChange: React.Dispatch<React.SetStateAction<VideoToSequenceParameters>>;
  onCreateSequence: () => void | Promise<void>;
  onOpenSequence: () => void;
  uploadAction: React.ReactNode;
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [videoDuration, setVideoDuration] = useState(0);
  const videoUrl = useObjectUrl(video?.url ?? "");
  const generatedSequence = currentTask?.type === "sequence_video_to_frames" && currentTask.result.sequence_id === sequence?.id ? sequence : null;
  const frameTaskRunning = currentTask?.type === "sequence_video_to_frames" && ["pending", "running"].includes(currentTask.status);
  const canCreateSequence = Boolean(videoUrl && !isTaskProcessing);
  const canOpenSequence = Boolean(generatedSequence?.frames.length);
  const estimatedFrames = useMemo(() => {
    const duration = Math.max(0, params.clip_end_seconds - params.clip_start_seconds);
    return Math.max(1, Math.round(duration * params.fps));
  }, [params.clip_end_seconds, params.clip_start_seconds, params.fps]);

  useEffect(() => {
    setVideoDuration(0);
  }, [video?.id]);

  useEffect(() => {
    if (!videoDuration) return;
    onParamsChange((current) => {
      const nextEnd = current.clip_end_seconds > 0 ? Math.min(current.clip_end_seconds, videoDuration) : Math.min(videoDuration, 2);
      const nextStart = Math.min(current.clip_start_seconds, Math.max(0, nextEnd - 0.1));
      return { ...current, clip_start_seconds: nextStart, clip_end_seconds: nextEnd };
    });
  }, [videoDuration, onParamsChange]);

  function seekClipStart() {
    if (!videoRef.current || !videoUrl) return;
    videoRef.current.currentTime = params.clip_start_seconds;
  }

  function keepPreviewInsideClip() {
    const target = videoRef.current;
    if (!target || !videoUrl) return;
    if (params.clip_end_seconds > params.clip_start_seconds && target.currentTime >= params.clip_end_seconds) {
      target.currentTime = params.clip_start_seconds;
      if (!target.paused) void target.play();
    }
  }

  return (
    <>
      <section className="preview-stage sequence-stage">
        <WorkbenchPreview key={`video-to-sequence-${video?.id ?? "empty"}`}>
          {!video ? (
            <EmptyCanvas />
          ) : (
            <div className="video-tool-canvas">
              {videoUrl ? (
                <video
                  ref={videoRef}
                  className="video-tool-preview"
                  src={videoUrl}
                  controls
                  playsInline
                  onLoadedMetadata={(event) => setVideoDuration(event.currentTarget.duration || 0)}
                  onTimeUpdate={keepPreviewInsideClip}
                />
              ) : (
                <span>正在加载视频...</span>
              )}
              {frameTaskRunning ? (
                <div className="video-tool-working">
                  <Sparkles size={22} />
                  <strong>正在抽帧和抠图</strong>
                </div>
              ) : null}
            </div>
          )}
        </WorkbenchPreview>
      </section>

      <aside className="settings-panel sequence-settings">
        {video ? (
          <VideoClipPanel
            params={params}
            duration={videoDuration}
            estimatedFrames={estimatedFrames}
            onParamsChange={onParamsChange}
            onSeekClipStart={seekClipStart}
          />
        ) : (
          <h2>转帧参数</h2>
        )}
        {generatedSequence ? (
          <div className="sequence-inline-result">
          <div className="diagnostics-heading">
            <div>
              <strong>生成结果</strong>
              <span>
                {generatedSequence.frame_count} 帧 · {generatedSequence.fps} FPS · {generatedSequence.canvas_width}×{generatedSequence.canvas_height}
              </span>
            </div>
            <button className="ghost compact" type="button" onClick={onOpenSequence}>
              <Play size={15} />
              继续调整
            </button>
          </div>
          <div className="timeline-strip">
            {generatedSequence.frames.map((frame) => (
              <button key={frame.id} className="frame-thumb" type="button">
                <GeneratedFrameThumb frameUrl={frame.preview_url} alt={frame.original_name} />
                <span>{frame.frame_index + 1}</span>
              </button>
            ))}
          </div>
          </div>
        ) : null}
        {error ? <p className="error-text">{error}</p> : null}
      </aside>

      <WorkbenchActionBar>
        {uploadAction}
        <button className="primary" type="button" disabled={!canCreateSequence || !canWrite} onClick={() => void onCreateSequence()}>
          {frameTaskRunning ? "处理中" : "转成序列帧"}
        </button>
        <button className="ghost" type="button" disabled={!canOpenSequence} onClick={onOpenSequence}>
          打开序列帧
        </button>
      </WorkbenchActionBar>
    </>
  );
}

function VideoGenerationPanel({
  params,
  onParamsChange,
}: {
  params: VideoSequenceGenerateParameters;
  onParamsChange: React.Dispatch<React.SetStateAction<VideoSequenceGenerateParameters>>;
}) {
  return (
    <>
      <h2>视频参数</h2>
      <label className="number-field">
        <span>动作</span>
        <select value={params.action} onChange={(event) => onParamsChange((current) => ({ ...current, action: event.target.value }))}>
          {ACTION_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <NumberField label="视频时长" value={params.duration} min={2} max={15} onChange={(value) => onParamsChange((current) => ({ ...current, duration: value }))} />
      <label className="number-field">
        <span>分辨率</span>
        <select value={params.resolution} onChange={(event) => onParamsChange((current) => ({ ...current, resolution: event.target.value }))}>
          <option value="480P">480P</option>
          <option value="720P">720P</option>
          <option value="1080P">1080P</option>
        </select>
      </label>
      <label className="number-field">
        <span>动作描述</span>
        <textarea rows={4} value={params.prompt} placeholder="留空会使用当前动作的游戏角色动画提示词。" onChange={(event) => onParamsChange((current) => ({ ...current, prompt: event.target.value }))} />
      </label>
      <details className="advanced-settings">
        <summary>高级参数</summary>
        <label className="number-field">
          <span>负向描述</span>
          <textarea rows={3} value={params.negative_prompt} onChange={(event) => onParamsChange((current) => ({ ...current, negative_prompt: event.target.value }))} />
        </label>
      </details>
    </>
  );
}

function VideoClipPanel({
  params,
  duration,
  estimatedFrames,
  onParamsChange,
  onSeekClipStart,
}: {
  params: VideoToSequenceParameters;
  duration: number;
  estimatedFrames: number;
  onParamsChange: React.Dispatch<React.SetStateAction<VideoToSequenceParameters>>;
  onSeekClipStart: () => void;
}) {
  const maxDuration = Math.max(duration, params.clip_end_seconds, 1);
  const startMax = Math.max(0, params.clip_end_seconds - 0.1);
  const endMin = Math.min(maxDuration, params.clip_start_seconds + 0.1);
  return (
    <>
      <h2>裁切与抽帧</h2>
      <div className="video-clip-summary">
        <strong>{duration ? `视频 ${duration.toFixed(1)} 秒` : "正在读取视频"}</strong>
        <span>预计导出 {estimatedFrames} 帧</span>
      </div>
      <label className="number-field">
        <span>动作</span>
        <select value={params.action} onChange={(event) => onParamsChange((current) => ({ ...current, action: event.target.value }))}>
          {ACTION_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label className="number-field">
        <span>开始时间</span>
        <input
          type="range"
          min={0}
          max={maxDuration}
          step={0.05}
          value={params.clip_start_seconds}
          onChange={(event) => onParamsChange((current) => ({ ...current, clip_start_seconds: Math.min(Number(event.target.value), startMax) }))}
          onMouseUp={onSeekClipStart}
          onTouchEnd={onSeekClipStart}
        />
      </label>
      <label className="number-field">
        <span>开始秒</span>
        <input
          type="number"
          min={0}
          max={startMax}
          step={0.05}
          value={Number(params.clip_start_seconds.toFixed(2))}
          onChange={(event) => onParamsChange((current) => ({ ...current, clip_start_seconds: Math.min(Number(event.target.value), startMax) }))}
        />
      </label>
      <label className="number-field">
        <span>结束时间</span>
        <input
          type="range"
          min={0}
          max={maxDuration}
          step={0.05}
          value={params.clip_end_seconds}
          onChange={(event) => onParamsChange((current) => ({ ...current, clip_end_seconds: Math.max(Number(event.target.value), endMin) }))}
          onMouseUp={onSeekClipStart}
          onTouchEnd={onSeekClipStart}
        />
      </label>
      <label className="number-field">
        <span>结束秒</span>
        <input
          type="number"
          min={endMin}
          max={maxDuration}
          step={0.05}
          value={Number(params.clip_end_seconds.toFixed(2))}
          onChange={(event) => onParamsChange((current) => ({ ...current, clip_end_seconds: Math.max(Number(event.target.value), endMin) }))}
        />
      </label>
      <NumberField label="目标 FPS" value={params.fps} min={1} max={60} onChange={(value) => onParamsChange((current) => ({ ...current, fps: value }))} />
      <NumberField label="输出尺寸" value={params.output_size} min={64} max={1024} onChange={(value) => onParamsChange((current) => ({ ...current, output_size: value }))} />
      <label className="setting-check">
        <input type="checkbox" checked={params.loop} onChange={(event) => onParamsChange((current) => ({ ...current, loop: event.target.checked }))} />
        循环动画
      </label>
      <details className="advanced-settings">
        <summary>高级参数</summary>
        <NumberField label="Alpha 平滑" value={params.alpha_smoothing} min={0} max={10} onChange={(value) => onParamsChange((current) => ({ ...current, alpha_smoothing: value }))} />
        <label className="setting-check">
          <input type="checkbox" checked={params.stabilize} onChange={(event) => onParamsChange((current) => ({ ...current, stabilize: event.target.checked }))} />
          稳定脚底基线
        </label>
      </details>
    </>
  );
}

function VideoApiConfirmDialog({ onCancel, onConfirm }: { onCancel: () => void; onConfirm: () => void }) {
  const modal = (
    <div className="failure-dialog-backdrop" role="presentation" onClick={onCancel}>
      <section className="api-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="video-api-confirm-title" onClick={(event) => event.stopPropagation()}>
        <div className="failure-dialog-title">
          <div>
            <span>外部 API</span>
            <strong id="video-api-confirm-title">确认调用视频生成 API？</strong>
          </div>
          <button className="ghost compact" type="button" onClick={onCancel}>
            取消
          </button>
        </div>
        <p>这次操作将调用外部视频 API，可能产生费用。确认后才会提交生成任务。</p>
        <div className="api-confirm-actions">
          <button className="ghost" type="button" onClick={onCancel}>
            暂不调用
          </button>
          <button className="primary" type="button" onClick={onConfirm}>
            确认调用 API
          </button>
        </div>
      </section>
    </div>
  );
  return createPortal(modal, document.body);
}

function GeneratedFrameThumb({ frameUrl, alt }: { frameUrl: string; alt: string }) {
  const url = useObjectUrl(frameUrl);
  return url ? <img src={url} alt={alt} /> : <em />;
}

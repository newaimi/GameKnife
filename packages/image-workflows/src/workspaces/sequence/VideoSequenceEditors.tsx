import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
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

const ACTION_OPTIONS = ["idle", "walk_down", "walk_up", "walk_left", "walk_right", "hurt", "death"];

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
  const { t } = useTranslation("workflows");
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
                <span>{t("sequence.video.loadingImage")}</span>
              )}
              {videoTaskRunning ? (
                <div className="video-tool-working">
                  <Sparkles size={22} />
                  <strong>{t("sequence.video.callingApi")}</strong>
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
            {t("sequence.video.editSource")}
          </button>
        </div>
        {error ? <p className="error-text">{error}</p> : null}
      </aside>

      <WorkbenchActionBar>
        {uploadAction}
        <button className="primary" type="button" disabled={!upload || isTaskProcessing || !canWrite} onClick={() => setConfirmOpen(true)}>
          {videoTaskRunning ? t("sequence.video.generating") : t("sequence.video.generate")}
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
          {t("sequence.video.download")}
        </a>
        <button className="ghost" type="button" disabled={!videoReady || !canWrite} onClick={onUseGeneratedVideo}>
          {t("sequence.video.sendToFrames")}
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
  const { t } = useTranslation("workflows");
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
                <span>{t("sequence.video.loadingVideo")}</span>
              )}
              {frameTaskRunning ? (
                <div className="video-tool-working">
                  <Sparkles size={22} />
                  <strong>{t("sequence.video.extracting")}</strong>
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
          <h2>{t("sequence.video.framesParameters")}</h2>
        )}
        {generatedSequence ? (
          <div className="sequence-inline-result">
          <div className="diagnostics-heading">
            <div>
              <strong>{t("sequence.video.result")}</strong>
              <span>{t("sequence.video.resultMeta", { count: generatedSequence.frame_count, fps: generatedSequence.fps, width: generatedSequence.canvas_width, height: generatedSequence.canvas_height })}</span>
            </div>
            <button className="ghost compact" type="button" onClick={onOpenSequence}>
              <Play size={15} />
              {t("sequence.video.continueEditing")}
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
          {frameTaskRunning ? t("sequence.video.processing") : t("sequence.video.createSequence")}
        </button>
        <button className="ghost" type="button" disabled={!canOpenSequence} onClick={onOpenSequence}>
          {t("sequence.video.openSequence")}
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
  const { t } = useTranslation("workflows");
  return (
    <>
      <h2>{t("sequence.video.parameters")}</h2>
      <label className="number-field">
        <span>{t("sequence.video.action")}</span>
        <select value={params.action} onChange={(event) => onParamsChange((current) => ({ ...current, action: event.target.value }))}>
          {ACTION_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {t(`sequence.actions.${option}`)}
            </option>
          ))}
        </select>
      </label>
      <NumberField label={t("sequence.video.duration")} value={params.duration} min={2} max={15} onChange={(value) => onParamsChange((current) => ({ ...current, duration: value }))} />
      <label className="number-field">
        <span>{t("sequence.video.resolution")}</span>
        <select value={params.resolution} onChange={(event) => onParamsChange((current) => ({ ...current, resolution: event.target.value }))}>
          <option value="480P">480P</option>
          <option value="720P">720P</option>
          <option value="1080P">1080P</option>
        </select>
      </label>
      <label className="number-field">
        <span>{t("sequence.video.prompt")}</span>
        <textarea rows={4} value={params.prompt} placeholder={t("sequence.video.promptPlaceholder")} onChange={(event) => onParamsChange((current) => ({ ...current, prompt: event.target.value }))} />
      </label>
      <details className="advanced-settings">
        <summary>{t("sequence.video.advanced")}</summary>
        <label className="number-field">
          <span>{t("sequence.video.negativePrompt")}</span>
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
  const { t } = useTranslation("workflows");
  const maxDuration = Math.max(duration, params.clip_end_seconds, 1);
  const startMax = Math.max(0, params.clip_end_seconds - 0.1);
  const endMin = Math.min(maxDuration, params.clip_start_seconds + 0.1);
  return (
    <>
      <h2>{t("sequence.video.clipParameters")}</h2>
      <div className="video-clip-summary">
        <strong>{duration ? t("sequence.video.durationValue", { duration: duration.toFixed(1) }) : t("sequence.video.reading")}</strong>
        <span>{t("sequence.video.estimatedFrames", { count: estimatedFrames })}</span>
      </div>
      <label className="number-field">
        <span>{t("sequence.video.action")}</span>
        <select value={params.action} onChange={(event) => onParamsChange((current) => ({ ...current, action: event.target.value }))}>
          {ACTION_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {t(`sequence.actions.${option}`)}
            </option>
          ))}
        </select>
      </label>
      <label className="number-field">
        <span>{t("sequence.video.startTime")}</span>
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
        <span>{t("sequence.video.startSeconds")}</span>
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
        <span>{t("sequence.video.endTime")}</span>
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
        <span>{t("sequence.video.endSeconds")}</span>
        <input
          type="number"
          min={endMin}
          max={maxDuration}
          step={0.05}
          value={Number(params.clip_end_seconds.toFixed(2))}
          onChange={(event) => onParamsChange((current) => ({ ...current, clip_end_seconds: Math.max(Number(event.target.value), endMin) }))}
        />
      </label>
      <NumberField label={t("sequence.video.targetFps")} value={params.fps} min={1} max={60} onChange={(value) => onParamsChange((current) => ({ ...current, fps: value }))} />
      <NumberField label={t("sequence.video.outputSize")} value={params.output_size} min={64} max={1024} onChange={(value) => onParamsChange((current) => ({ ...current, output_size: value }))} />
      <label className="setting-check">
        <input type="checkbox" checked={params.loop} onChange={(event) => onParamsChange((current) => ({ ...current, loop: event.target.checked }))} />
        {t("sequence.video.loop")}
      </label>
      <details className="advanced-settings">
        <summary>{t("sequence.video.advanced")}</summary>
        <NumberField label={t("sequence.video.alphaSmoothing")} value={params.alpha_smoothing} min={0} max={10} onChange={(value) => onParamsChange((current) => ({ ...current, alpha_smoothing: value }))} />
        <label className="setting-check">
          <input type="checkbox" checked={params.stabilize} onChange={(event) => onParamsChange((current) => ({ ...current, stabilize: event.target.checked }))} />
          {t("sequence.video.stabilize")}
        </label>
      </details>
    </>
  );
}

function VideoApiConfirmDialog({ onCancel, onConfirm }: { onCancel: () => void; onConfirm: () => void }) {
  const { t } = useTranslation("workflows");
  const modal = (
    <div className="failure-dialog-backdrop" role="presentation" onClick={onCancel}>
      <section className="api-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="video-api-confirm-title" onClick={(event) => event.stopPropagation()}>
        <div className="failure-dialog-title">
          <div>
            <span>{t("sequence.video.externalApi")}</span>
            <strong id="video-api-confirm-title">{t("sequence.video.confirmTitle")}</strong>
          </div>
          <button className="ghost compact" type="button" onClick={onCancel}>
            {t("sequence.video.cancel")}
          </button>
        </div>
        <p>{t("sequence.video.confirmDescription")}</p>
        <div className="api-confirm-actions">
          <button className="ghost" type="button" onClick={onCancel}>
            {t("sequence.video.decline")}
          </button>
          <button className="primary" type="button" onClick={onConfirm}>
            {t("sequence.video.confirm")}
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

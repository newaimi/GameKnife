import React, { useEffect, useMemo, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";
import type { SequenceCleanParameters, SequenceFrameResponse, SequenceResponse } from "@gameknife/shared-types";
import { NumberField, WorkbenchPreview } from "@gameknife/ui-kit";
import type { ManualEditSource } from "../../types/manualEdit";
import { gameKnifeApiClient } from "@gameknife/api-client";
import { EmptyCanvas } from "../../components/ImageComparePreview";
import { clamp } from "../../utils/math";

export function SequenceEditor({
  sequence,
  sequences,
  params,
  error,
  canWrite,
  onSelect,
  onSaveSettings,
  onSaveFrames,
  onParamsChange,
  onDelete,
  onManualEdit,
}: {
  sequence: SequenceResponse | null;
  sequences: SequenceResponse[];
  params: SequenceCleanParameters;
  error: string;
  canWrite: boolean;
  onSelect: (sequenceId: string) => void | Promise<void>;
  onSaveSettings: (sequence: SequenceResponse, params?: SequenceCleanParameters) => void | Promise<void>;
  onSaveFrames: (frames: SequenceFrameResponse[]) => void | Promise<void>;
  onParamsChange: React.Dispatch<React.SetStateAction<SequenceCleanParameters>>;
  onDelete: (sequenceId: string) => void | Promise<void>;
  onManualEdit: (source: Pick<ManualEditSource, "name" | "url" | "sourceFileId" | "sourceContext">) => void | Promise<void>;
}) {
  const [playing, setPlaying] = useState(false);
  const [showOnionSkin, setShowOnionSkin] = useState(false);
  const [showDifferenceMap, setShowDifferenceMap] = useState(false);
  const [referenceFrameId, setReferenceFrameId] = useState("");
  const [activeFrameId, setActiveFrameId] = useState("");
  const [draftSequence, setDraftSequence] = useState<SequenceResponse | null>(sequence);
  const [draftFrames, setDraftFrames] = useState<SequenceFrameResponse[]>(sequence?.frames ?? []);
  const savedSequence = useRef(sequence);
  const frames = useMemo(() => draftFrames.slice().sort((first, second) => first.frame_index - second.frame_index), [draftFrames]);
  const enabledFrames = useMemo(() => frames.filter((frame) => frame.enabled), [frames]);
  const navigationFrames = enabledFrames.length ? enabledFrames : frames;
  const canNavigateFrames = navigationFrames.length > 1;
  const activeFrame = frames.find((frame) => frame.id === activeFrameId) ?? enabledFrames[0] ?? frames[0] ?? null;
  const referenceFrame = frames.find((frame) => frame.id === referenceFrameId) ?? enabledFrames[0] ?? frames[0] ?? null;
  const activeIndex = activeFrame ? Math.max(0, enabledFrames.findIndex((frame) => frame.id === activeFrame.id)) : 0;
  const previousFrame = enabledFrames[(activeIndex - 1 + enabledFrames.length) % enabledFrames.length];
  const nextFrame = enabledFrames[(activeIndex + 1) % enabledFrames.length];
  const loadPreview = useRef<(source: string) => Promise<string>>(() => Promise.resolve(""));
  const [previews, setPreviews] = useState<{ sequenceId: string; urls: Record<string, string>; error: string }>({ sequenceId: "", urls: {}, error: "" });
  const previewUrls = previews.sequenceId === sequence?.id ? previews.urls : {};
  const activeUrl = previewUrls[activeFrame?.preview_url ?? ""] ?? "";
  const referenceUrl = previewUrls[referenceFrame?.preview_url ?? ""] ?? "";
  const previousUrl = previewUrls[previousFrame?.preview_url ?? ""] ?? "";
  const nextUrl = previewUrls[nextFrame?.preview_url ?? ""] ?? "";
  const [presentedFrame, setPresentedFrame] = useState<{ sequenceId: string; frame: SequenceFrameResponse; url: string } | null>(null);
  const visibleFrame = activeUrl && activeFrame ? { frame: activeFrame, url: activeUrl } : presentedFrame?.sequenceId === sequence?.id ? presentedFrame : null;
  const previewSources = useMemo(() => JSON.stringify([...new Set((draftSequence?.id === sequence?.id ? frames : []).map((frame) => frame.preview_url))].sort()), [frames, draftSequence?.id, sequence?.id]);
  const differenceMap = useFrameDifferenceMap(referenceUrl, activeUrl, showDifferenceMap && Boolean(referenceFrame && activeFrame && referenceFrame.id !== activeFrame.id));
  const diagnostics = readSequenceDiagnostics(frames, referenceFrame, activeFrame, differenceMap);

  useEffect(() => {
    const sequenceId = sequence?.id ?? "";
    const requests = new Map<string, Promise<string>>();
    const objectUrls = new Set<string>();
    const failedSources = new Set<string>();
    let alive = true;
    setPreviews({ sequenceId, urls: {}, error: "" });
    // The timeline already displays every frame. Share its downloads and decoded images
    // with playback, references and onion skins until the sequence or its source files change.
    const load = (source: string): Promise<string> => {
      const current = requests.get(source);
      if (current) return current;
      let objectUrl = "";
      const request = gameKnifeApiClient.requestBlob(source).then(async (blob) => {
        if (!alive) return "";
        const url = URL.createObjectURL(blob);
        objectUrl = url;
        objectUrls.add(url);
        const image = new Image();
        image.src = url;
        await image.decode();
        if (!alive) return "";
        failedSources.delete(source);
        setPreviews((current) => ({ ...current, urls: { ...current.urls, [source]: url }, error: failedSources.size ? "帧预览加载失败。" : "" }));
        return url;
      }).catch(() => {
        // A later play action may retry this frame without discarding successful previews.
        requests.delete(source);
        if (objectUrls.delete(objectUrl)) URL.revokeObjectURL(objectUrl);
        if (alive) {
          failedSources.add(source);
          setPreviews((current) => ({ ...current, error: "帧预览加载失败。" }));
        }
        return "";
      });
      requests.set(source, request);
      return request;
    };
    loadPreview.current = load;
    for (const source of JSON.parse(previewSources) as string[]) void load(source);
    return () => {
      alive = false;
      for (const url of objectUrls) URL.revokeObjectURL(url);
      objectUrls.clear();
    };
  }, [sequence?.id, previewSources]);

  useEffect(() => {
    if (sequence && activeFrame && activeUrl) setPresentedFrame({ sequenceId: sequence.id, frame: activeFrame, url: activeUrl });
  }, [sequence?.id, activeFrame, activeUrl]);

  useEffect(() => setPlaying(false), [sequence?.id]);

  useEffect(() => {
    const previous = savedSequence.current;
    savedSequence.current = sequence;
    if (!sequence || sequence.id !== previous?.id) {
      setDraftSequence(sequence);
      setDraftFrames(sequence?.frames ?? []);
    } else {
      // Saving settings and saving frames return the whole sequence. Accept persisted
      // fields while keeping edits to the other operation against their previous baseline.
      setDraftSequence((current) => current ? {
        ...sequence,
        name: current.name.trim() !== previous.name && current.name.trim() !== sequence.name ? current.name : sequence.name,
        fps: current.fps !== previous.fps ? current.fps : sequence.fps,
        loop: current.loop !== previous.loop ? current.loop : sequence.loop,
        canvas_width: current.canvas_width !== previous.canvas_width ? current.canvas_width : sequence.canvas_width,
        canvas_height: current.canvas_height !== previous.canvas_height ? current.canvas_height : sequence.canvas_height,
        anchor_mode: current.anchor_mode !== previous.anchor_mode ? current.anchor_mode : sequence.anchor_mode,
        anchor_x: current.anchor_x !== previous.anchor_x ? current.anchor_x : sequence.anchor_x,
        anchor_y: current.anchor_y !== previous.anchor_y ? current.anchor_y : sequence.anchor_y,
      } : sequence);
      setDraftFrames((current) => {
        const drafts = new Map(current.map((frame) => [frame.id, frame]));
        const saved = new Map(previous.frames.map((frame) => [frame.id, frame]));
        return sequence.frames.map((frame) => {
          const draft = drafts.get(frame.id);
          const baseline = saved.get(frame.id);
          if (!draft || !baseline) return frame;
          return {
            ...frame,
            frame_index: draft.frame_index !== baseline.frame_index ? draft.frame_index : frame.frame_index,
            offset_x: draft.offset_x !== baseline.offset_x ? draft.offset_x : frame.offset_x,
            offset_y: draft.offset_y !== baseline.offset_y ? draft.offset_y : frame.offset_y,
            enabled: draft.enabled !== baseline.enabled ? draft.enabled : frame.enabled,
          };
        });
      });
    }
    setActiveFrameId((current) => {
      if (sequence?.frames.some((frame) => frame.id === current)) return current;
      return sequence?.frames.find((frame) => frame.enabled)?.id ?? sequence?.frames[0]?.id ?? "";
    });
  }, [sequence?.id, sequence?.updated_at]);

  useEffect(() => {
    // Reference selection belongs to cleaning parameters and must not reset unrelated drafts.
    setReferenceFrameId((current) => {
      const savedReference = typeof params.reference_frame_id === "string" ? params.reference_frame_id : "";
      if (savedReference && sequence?.frames.some((frame) => frame.id === savedReference)) return savedReference;
      if (sequence?.frames.some((frame) => frame.id === current)) return current;
      return sequence?.frames.find((frame) => frame.enabled)?.id ?? sequence?.frames[0]?.id ?? "";
    });
  }, [sequence?.id, sequence?.updated_at, params.reference_frame_id]);

  useEffect(() => {
    if (!playing) return;
    if (!enabledFrames.length) {
      setPlaying(false);
      return;
    }
    const currentIndex = enabledFrames.findIndex((frame) => frame.id === activeFrameId);
    if (currentIndex < 0) {
      setActiveFrameId(enabledFrames[0].id);
      return;
    }
    const current = enabledFrames[currentIndex];
    let alive = true;
    let timer: number | undefined;
    void loadPreview.current(current.preview_url).then((url) => {
      if (!alive) return;
      if (!url) {
        setPlaying(false);
        return;
      }
      const fps = draftSequence?.fps ?? 12;
      // FPS edits scale positive frame timings without overwriting a custom rhythm.
      // The repository applies the same ratio when settings are saved; zero keeps the FPS fallback.
      const duration = current.duration_ms > 0 ? Math.max(1, Math.round(current.duration_ms * (sequence?.fps ?? fps) / fps)) : 1000 / fps;
      timer = window.setTimeout(() => {
        if (currentIndex === enabledFrames.length - 1 && !draftSequence?.loop) {
          setPlaying(false);
          return;
        }
        const next = enabledFrames[(currentIndex + 1) % enabledFrames.length];
        // Keep the current image visible while a cold next frame is downloading or decoding.
        void loadPreview.current(next.preview_url).then((nextUrl) => {
          if (!alive) return;
          if (nextUrl) setActiveFrameId(next.id);
          else setPlaying(false);
        });
      }, duration);
    });
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [playing, enabledFrames, activeFrameId, draftSequence?.fps, draftSequence?.loop, sequence?.fps, previewSources]);

  const updateFrame = (frameId: string, patch: Partial<SequenceFrameResponse>) => {
    setDraftFrames((current) => current.map((frame) => (frame.id === frameId ? { ...frame, ...patch } : frame)));
  };

  const reorderFrame = (frameId: string, direction: -1 | 1) => {
    const index = frames.findIndex((frame) => frame.id === frameId);
    const targetIndex = index + direction;
    if (index < 0 || targetIndex < 0 || targetIndex >= frames.length) return;
    const nextFrames = frames.slice();
    const [item] = nextFrames.splice(index, 1);
    nextFrames.splice(targetIndex, 0, item);
    setDraftFrames(nextFrames.map((frame, frameIndex) => ({ ...frame, frame_index: frameIndex })));
  };

  const selectNeighborFrame = (direction: -1 | 1) => {
    if (!canNavigateFrames) return;
    // Navigation follows enabled frames so manual stepping matches playback and export.
    const currentIndex = Math.max(0, navigationFrames.findIndex((frame) => frame.id === activeFrame?.id));
    const nextIndex = (currentIndex + direction + navigationFrames.length) % navigationFrames.length;
    setPlaying(false);
    setActiveFrameId(navigationFrames[nextIndex].id);
  };

  const lockReferenceFrame = () => {
    if (!activeFrame) return;
    setReferenceFrameId(activeFrame.id);
    onParamsChange((current) => ({ ...current, reference_frame_id: activeFrame.id }));
  };

  if (!sequence || !draftSequence) {
    return (
      <>
        <section className="preview-stage sequence-stage">
          <WorkbenchPreview key="sequence-empty">
            <EmptyCanvas />
          </WorkbenchPreview>
        </section>
        <aside className="settings-panel">
          <h2>序列帧</h2>
          {error ? <p className="error-text">{error}</p> : null}
        </aside>
      </>
    );
  }

  return (
    <>
      <section className="preview-stage sequence-stage">
        <WorkbenchPreview
          key={`sequence-${sequence.id}`}
          // The sequence canvas has fixed bounds; centering a full-size wrapper leaves it under the tool panel.
          contentMode="intrinsic"
          toolbarControls={
            <>
              <button className="frame-nav" type="button" disabled={!canNavigateFrames} onClick={() => selectNeighborFrame(-1)}>
                上一帧
              </button>
              <button className="frame-nav" type="button" disabled={!canNavigateFrames} onClick={() => selectNeighborFrame(1)}>
                下一帧
              </button>
            </>
          }
        >
          <div className="sequence-canvas">
            {showOnionSkin && previousUrl ? <img className="onion-frame previous" src={previousUrl} alt="" aria-hidden="true" /> : null}
            {visibleFrame ? <img className="active-frame" src={visibleFrame.url} alt={visibleFrame.frame.original_name} /> : <span>正在加载帧...</span>}
            {showOnionSkin && nextUrl ? <img className="onion-frame next" src={nextUrl} alt="" aria-hidden="true" /> : null}
            {showDifferenceMap && differenceMap.url ? <img className="difference-map" src={differenceMap.url} alt="当前帧与参考帧的差异热力图" /> : null}
            <div className="anchor-line horizontal" />
            <div className="anchor-line vertical" />
          </div>
        </WorkbenchPreview>
      </section>

      <aside className="settings-panel sequence-settings">
        <h2>序列设置</h2>
        <div className="sequence-toggle-group" aria-label="序列帧预览控制">
          <button className="ghost compact" type="button" disabled={!enabledFrames.length} onClick={() => {
            if (!playing && (!activeFrame?.enabled || (!draftSequence.loop && activeIndex === enabledFrames.length - 1))) setActiveFrameId(enabledFrames[0].id);
            setPlaying((current) => !current);
          }}>
            {playing ? <Pause size={16} /> : <Play size={16} />}
            {playing ? "暂停" : "播放"}
          </button>
          <button
            className={`ghost compact ${showOnionSkin ? "active-soft" : ""}`}
            type="button"
            aria-pressed={showOnionSkin}
            onClick={() => setShowOnionSkin((current) => !current)}
          >
            洋葱皮
          </button>
          <button className="ghost compact" type="button" disabled={!activeFrame} onClick={lockReferenceFrame}>
            锁参考
          </button>
          <button
            className={`ghost compact ${showDifferenceMap ? "active-soft" : ""}`}
            type="button"
            disabled={!referenceFrame || !activeFrame}
            aria-pressed={showDifferenceMap}
            onClick={() => setShowDifferenceMap((current) => !current)}
          >
            差异图
          </button>
        </div>
        <button
          className="ghost install-button"
          type="button"
          disabled={!activeFrame || !activeUrl || !canWrite}
          onClick={() =>
            activeFrame && activeUrl
              ? void onManualEdit({
                  name: activeFrame.original_name,
                  url: activeUrl,
                  sourceFileId: activeFrame.processed_asset_id ?? activeFrame.source_asset_id,
                  sourceContext: "sequence_frame",
                })
              : undefined
          }
        >
          编辑帧
        </button>
        <label className="number-field">
          <span>当前序列</span>
          <select value={sequence.id} title={sequence.name} onChange={(event) => void onSelect(event.target.value)}>
            {sequences.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label className="number-field">
          <span>名称</span>
          <input value={draftSequence.name} title={draftSequence.name} onChange={(event) => setDraftSequence({ ...draftSequence, name: event.target.value })} />
        </label>
        <NumberField label="FPS" value={draftSequence.fps} min={1} max={60} onChange={(fps) => setDraftSequence({ ...draftSequence, fps })} />
        <NumberField
          label="画布宽"
          value={draftSequence.canvas_width}
          min={0}
          max={4096}
          onChange={(canvas_width) => setDraftSequence({ ...draftSequence, canvas_width })}
        />
        <NumberField
          label="画布高"
          value={draftSequence.canvas_height}
          min={0}
          max={4096}
          onChange={(canvas_height) => setDraftSequence({ ...draftSequence, canvas_height })}
        />
        <label className="setting-check">
          <input type="checkbox" checked={draftSequence.loop} onChange={(event) => setDraftSequence({ ...draftSequence, loop: event.target.checked })} />
          循环播放
        </label>
        <label className="number-field">
          <span>锚点策略</span>
          <select value={draftSequence.anchor_mode} onChange={(event) => setDraftSequence({ ...draftSequence, anchor_mode: event.target.value })}>
            <option value="bottom_center">底部中心</option>
            <option value="center">画布中心</option>
          </select>
        </label>

        <h2>清洗参数</h2>
        <NumberField label="Alpha 阈值" value={params.alpha_threshold} min={0} max={255} onChange={(value) => onParamsChange((current) => ({ ...current, alpha_threshold: value }))} />
        <NumberField label="Alpha 平滑" value={params.alpha_smoothing} min={0} max={10} onChange={(value) => onParamsChange((current) => ({ ...current, alpha_smoothing: value }))} />
        <NumberField label="裁切留边" value={params.trim_padding} min={0} max={80} onChange={(value) => onParamsChange((current) => ({ ...current, trim_padding: value }))} />
        <NumberField label="画布留边" value={params.canvas_padding} min={0} max={120} onChange={(value) => onParamsChange((current) => ({ ...current, canvas_padding: value }))} />
        <label className="setting-check">
          <input type="checkbox" checked={params.denoise} onChange={(event) => onParamsChange((current) => ({ ...current, denoise: event.target.checked }))} />
          去除半透明噪点
        </label>
        <h2>一致性修复</h2>
        <label className="setting-check">
          <input type="checkbox" checked={params.color_match} onChange={(event) => onParamsChange((current) => ({ ...current, color_match: event.target.checked }))} />
          颜色统一
        </label>
        <label className="setting-check">
          <input type="checkbox" checked={params.stabilize} onChange={(event) => onParamsChange((current) => ({ ...current, stabilize: event.target.checked }))} />
          保守稳定
        </label>
        <NumberField
          label="稳定强度"
          value={params.stabilize_strength}
          min={0}
          max={100}
          onChange={(value) => onParamsChange((current) => ({ ...current, stabilize_strength: value }))}
        />
        <p className="helper-text">参考帧：{referenceFrame ? `${referenceFrame.frame_index + 1} · ${referenceFrame.original_name}` : "未锁定"}</p>
        <button className="primary install-button" type="button" disabled={!canWrite} onClick={() => void onSaveSettings(draftSequence, params)}>
          保存设置
        </button>
        <div className="export-stack">
          <button className="ghost danger-text" type="button" disabled={!canWrite} onClick={() => void onDelete(sequence.id)}>
            删除序列
          </button>
        </div>

        <SequenceDiagnosticsPanel diagnostics={diagnostics} referenceFrame={referenceFrame} differenceMap={differenceMap} />

        <div className="timeline-strip">
          {frames.map((frame) => (
            <button
              key={frame.id}
              className={`frame-thumb ${frame.id === activeFrame?.id ? "active" : ""} ${frame.id === referenceFrame?.id ? "reference" : ""} ${frame.enabled ? "" : "disabled"}`}
              type="button"
              onClick={() => { setPlaying(false); setActiveFrameId(frame.id); }}
            >
              {previewUrls[frame.preview_url] ? <img src={previewUrls[frame.preview_url]} alt={frame.original_name} /> : <em />}
              <span>{frame.frame_index + 1}</span>
            </button>
          ))}
        </div>

        {activeFrame ? (
          <div className="frame-editor">
            <strong>{activeFrame.original_name}</strong>
            <button className="ghost compact" type="button" onClick={() => reorderFrame(activeFrame.id, -1)}>
              前移
            </button>
            <button className="ghost compact" type="button" onClick={() => reorderFrame(activeFrame.id, 1)}>
              后移
            </button>
            <button className="ghost compact" type="button" onClick={() => updateFrame(activeFrame.id, { enabled: !activeFrame.enabled })}>
              {activeFrame.enabled ? "停用帧" : "启用帧"}
            </button>
            <label>
              X 偏移
              <input type="number" value={activeFrame.offset_x} onChange={(event) => updateFrame(activeFrame.id, { offset_x: Number(event.target.value) })} />
            </label>
            <label>
              Y 偏移
              <input type="number" value={activeFrame.offset_y} onChange={(event) => updateFrame(activeFrame.id, { offset_y: Number(event.target.value) })} />
            </label>
            <button className="primary compact" type="button" disabled={!canWrite} onClick={() => void onSaveFrames(draftFrames)}>
              保存帧调整
            </button>
          </div>
        ) : null}
        {error ? <p className="error-text">{error}</p> : null}
        {previews.sequenceId === sequence.id && previews.error ? <p className="error-text">{previews.error}</p> : null}
      </aside>
    </>
  );
}

type FrameDifferenceMap = {
  url: string;
  score: number;
  changedPct: number;
  status: "idle" | "loading" | "ready" | "failed";
};

type SequenceDiagnostic = {
  tone: "ok" | "warn" | "danger";
  title: string;
  detail: string;
};

type SequenceDiagnostics = {
  metrics: Array<{ label: string; value: string }>;
  notes: SequenceDiagnostic[];
};

function SequenceDiagnosticsPanel({
  diagnostics,
  referenceFrame,
  differenceMap,
}: {
  diagnostics: SequenceDiagnostics;
  referenceFrame: SequenceFrameResponse | null;
  differenceMap: FrameDifferenceMap;
}) {
  return (
    <div className="sequence-diagnostics">
      <div className="diagnostics-heading">
        <div>
          <strong>一致性检查</strong>
          <span>{referenceFrame ? `参考帧 ${referenceFrame.frame_index + 1}` : "未锁定参考帧"}</span>
        </div>
        <span className={`diff-status ${differenceMap.status}`}>{differenceMap.status === "loading" ? "分析中" : differenceMap.status === "ready" ? "差异已生成" : "本地分析"}</span>
      </div>
      <div className="diagnostic-metrics">
        {diagnostics.metrics.map((metric) => (
          <div key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
          </div>
        ))}
      </div>
      <div className="diagnostic-notes">
        {diagnostics.notes.map((note) => (
          <p key={`${note.title}-${note.detail}`} className={`diagnostic-note ${note.tone}`}>
            <strong>{note.title}</strong>
            {note.detail}
          </p>
        ))}
      </div>
    </div>
  );
}

function useFrameDifferenceMap(referenceUrl: string, activeUrl: string, enabled: boolean): FrameDifferenceMap {
  const [differenceMap, setDifferenceMap] = useState<FrameDifferenceMap>({ url: "", score: 0, changedPct: 0, status: "idle" });

  useEffect(() => {
    if (!enabled || !referenceUrl || !activeUrl) {
      setDifferenceMap({ url: "", score: 0, changedPct: 0, status: "idle" });
      return;
    }

    let cancelled = false;
    setDifferenceMap((current) => ({ ...current, status: "loading" }));
    void buildFrameDifferenceMap(referenceUrl, activeUrl)
      .then((nextMap) => {
        if (!cancelled) setDifferenceMap(nextMap);
      })
      .catch(() => {
        if (!cancelled) setDifferenceMap({ url: "", score: 0, changedPct: 0, status: "failed" });
      });

    return () => {
      cancelled = true;
    };
  }, [referenceUrl, activeUrl, enabled]);

  return differenceMap;
}

async function buildFrameDifferenceMap(referenceUrl: string, activeUrl: string): Promise<FrameDifferenceMap> {
  const [referenceImage, activeImage] = await Promise.all([loadPreviewImage(referenceUrl), loadPreviewImage(activeUrl)]);
  const width = Math.max(referenceImage.naturalWidth, activeImage.naturalWidth, 1);
  const height = Math.max(referenceImage.naturalHeight, activeImage.naturalHeight, 1);
  const referenceCanvas = drawAlignedImage(referenceImage, width, height);
  const activeCanvas = drawAlignedImage(activeImage, width, height);
  const referencePixels = referenceCanvas.getContext("2d")?.getImageData(0, 0, width, height);
  const activePixels = activeCanvas.getContext("2d")?.getImageData(0, 0, width, height);
  if (!referencePixels || !activePixels) {
    return { url: "", score: 0, changedPct: 0, status: "failed" };
  }

  const heatCanvas = document.createElement("canvas");
  heatCanvas.width = width;
  heatCanvas.height = height;
  const heatContext = heatCanvas.getContext("2d");
  if (!heatContext) return { url: "", score: 0, changedPct: 0, status: "failed" };
  const heatPixels = heatContext.createImageData(width, height);
  let diffTotal = 0;
  let visibleCount = 0;
  let changedCount = 0;

  for (let index = 0; index < referencePixels.data.length; index += 4) {
    const visible = Math.max(referencePixels.data[index + 3], activePixels.data[index + 3]) > 8;
    if (!visible) continue;
    const diff =
      (Math.abs(referencePixels.data[index] - activePixels.data[index]) +
        Math.abs(referencePixels.data[index + 1] - activePixels.data[index + 1]) +
        Math.abs(referencePixels.data[index + 2] - activePixels.data[index + 2]) +
        Math.abs(referencePixels.data[index + 3] - activePixels.data[index + 3])) /
      4;
    visibleCount += 1;
    diffTotal += diff;
    if (diff > 24) changedCount += 1;
    const intensity = clamp((diff - 18) / 120, 0, 1);
    heatPixels.data[index] = 255;
    heatPixels.data[index + 1] = Math.round(180 * (1 - intensity));
    heatPixels.data[index + 2] = 0;
    heatPixels.data[index + 3] = Math.round(210 * intensity);
  }

  heatContext.putImageData(heatPixels, 0, 0);
  return {
    url: heatCanvas.toDataURL("image/png"),
    score: visibleCount ? diffTotal / visibleCount : 0,
    changedPct: visibleCount ? (changedCount / visibleCount) * 100 : 0,
    status: "ready",
  };
}

function loadPreviewImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("图片读取失败。"));
    image.src = url;
  });
}

function drawAlignedImage(image: HTMLImageElement, width: number, height: number) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (context) {
    // 差异图使用底部中心对齐，和角色序列默认锚点一致，优先暴露角色自身漂移而不是画布尺寸差。
    context.drawImage(image, Math.round((width - image.naturalWidth) / 2), height - image.naturalHeight);
  }
  return canvas;
}

function readSequenceDiagnostics(
  frames: SequenceFrameResponse[],
  referenceFrame: SequenceFrameResponse | null,
  activeFrame: SequenceFrameResponse | null,
  differenceMap: FrameDifferenceMap,
): SequenceDiagnostics {
  const enabledFrames = frames.filter((frame) => frame.enabled);
  const widths = enabledFrames.map((frame) => frame.bbox[2]);
  const heights = enabledFrames.map((frame) => frame.bbox[3]);
  const bottoms = enabledFrames.map((frame) => frame.bbox[1] + frame.bbox[3]);
  const widthJitter = readRange(widths);
  const heightJitter = readRange(heights);
  const baselineJitter = readRange(bottoms);
  const notes: SequenceDiagnostic[] = [];

  if (!referenceFrame) {
    notes.push({ tone: "warn", title: "参考帧", detail: "先锁定一张最稳定的帧，再做颜色统一和差异检查。" });
  }
  if (enabledFrames.length < 8) {
    notes.push({ tone: "warn", title: "关键阶段", detail: "帧数偏少，走路循环容易缺少接触、交叉或过渡阶段。" });
  } else {
    notes.push({ tone: "ok", title: "关键阶段", detail: "帧数够用，但交叉帧、接触帧仍需要在时间轴逐帧确认。" });
  }
  if (widthJitter > 8 || heightJitter > 6) {
    notes.push({ tone: "warn", title: "轮廓漂移", detail: "主体尺寸变化偏大，建议先清洗并开启颜色统一。" });
  }
  if (baselineJitter > 3) {
    notes.push({ tone: "warn", title: "脚底基线", detail: "底部位置变化明显，导出前需要统一画布和底部中心锚点。" });
  }
  if (differenceMap.status === "ready" && activeFrame && referenceFrame && activeFrame.id !== referenceFrame.id) {
    const tone = differenceMap.score > 18 || differenceMap.changedPct > 30 ? "danger" : differenceMap.score > 10 ? "warn" : "ok";
    notes.push({
      tone,
      title: "当前差异",
      detail: `与参考帧可见区域差异 ${differenceMap.score.toFixed(1)}，变化面积 ${differenceMap.changedPct.toFixed(1)}%。`,
    });
  }

  return {
    metrics: [
      { label: "尺寸漂移", value: `${widthJitter}×${heightJitter}px` },
      { label: "脚底漂移", value: `${baselineJitter}px` },
      { label: "当前差异", value: differenceMap.status === "ready" ? differenceMap.score.toFixed(1) : "-" },
    ],
    notes,
  };
}

function readRange(values: number[]) {
  if (!values.length) return 0;
  return Math.max(...values) - Math.min(...values);
}

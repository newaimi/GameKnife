import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "@gameknife/i18n";
import { Pause, Play } from "lucide-react";
import type { SequenceCleanParameters, SequenceFrameResponse, SequenceResponse } from "@gameknife/shared-types";
import { NumberField, WorkbenchPreview } from "@gameknife/ui-kit";
import type { ManualEditSource } from "../../types/manualEdit";
import { useObjectUrl } from "../../utils/objectUrl";
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
  const { t } = useTranslation("workflows");
  const [playing, setPlaying] = useState(false);
  const [showOnionSkin, setShowOnionSkin] = useState(false);
  const [showDifferenceMap, setShowDifferenceMap] = useState(false);
  const [referenceFrameId, setReferenceFrameId] = useState("");
  const [activeFrameId, setActiveFrameId] = useState("");
  const [draftSequence, setDraftSequence] = useState<SequenceResponse | null>(sequence);
  const [draftFrames, setDraftFrames] = useState<SequenceFrameResponse[]>(sequence?.frames ?? []);
  const frames = draftFrames.slice().sort((first, second) => first.frame_index - second.frame_index);
  const enabledFrames = frames.filter((frame) => frame.enabled);
  const navigationFrames = enabledFrames.length ? enabledFrames : frames;
  const canNavigateFrames = navigationFrames.length > 1;
  const activeFrame = frames.find((frame) => frame.id === activeFrameId) ?? enabledFrames[0] ?? frames[0] ?? null;
  const referenceFrame = frames.find((frame) => frame.id === referenceFrameId) ?? enabledFrames[0] ?? frames[0] ?? null;
  const activeIndex = activeFrame ? Math.max(0, enabledFrames.findIndex((frame) => frame.id === activeFrame.id)) : 0;
  const previousFrame = enabledFrames[(activeIndex - 1 + enabledFrames.length) % enabledFrames.length];
  const nextFrame = enabledFrames[(activeIndex + 1) % enabledFrames.length];
  const activeUrl = useObjectUrl(activeFrame?.preview_url ?? "");
  const referenceUrl = useObjectUrl(referenceFrame?.preview_url ?? "");
  const previousUrl = useObjectUrl(previousFrame?.preview_url ?? "");
  const nextUrl = useObjectUrl(nextFrame?.preview_url ?? "");
  const differenceMap = useFrameDifferenceMap(referenceUrl, activeUrl, showDifferenceMap && Boolean(referenceFrame && activeFrame && referenceFrame.id !== activeFrame.id));
  const diagnostics = readSequenceDiagnostics(frames, referenceFrame, activeFrame, differenceMap, t);

  useEffect(() => {
    setDraftSequence(sequence);
    setDraftFrames(sequence?.frames ?? []);
    setActiveFrameId((current) => {
      if (sequence?.frames.some((frame) => frame.id === current)) return current;
      return sequence?.frames.find((frame) => frame.enabled)?.id ?? sequence?.frames[0]?.id ?? "";
    });
    setReferenceFrameId((current) => {
      const savedReference = typeof params.reference_frame_id === "string" ? params.reference_frame_id : "";
      if (savedReference && sequence?.frames.some((frame) => frame.id === savedReference)) return savedReference;
      if (sequence?.frames.some((frame) => frame.id === current)) return current;
      return sequence?.frames.find((frame) => frame.enabled)?.id ?? sequence?.frames[0]?.id ?? "";
    });
  }, [sequence?.id, sequence?.updated_at, params.reference_frame_id]);

  useEffect(() => {
    if (!playing || enabledFrames.length <= 1) return;
    const fps = Math.max(1, draftSequence?.fps ?? 12);
    const timer = window.setInterval(() => {
      setActiveFrameId((current) => {
        const currentIndex = enabledFrames.findIndex((frame) => frame.id === current);
        const next = enabledFrames[(currentIndex + 1) % enabledFrames.length];
        return next?.id ?? current;
      });
    }, 1000 / fps);
    return () => window.clearInterval(timer);
  }, [playing, enabledFrames, draftSequence?.fps]);

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
    // Frame navigation follows the same enabled-frame set used by playback and export.
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
          <h2>{t("sequence.editor.title")}</h2>
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
          toolbarControls={
            <>
              <button className="frame-nav" type="button" disabled={!canNavigateFrames} onClick={() => selectNeighborFrame(-1)}>
                {t("sequence.editor.previousFrame")}
              </button>
              <button className="frame-nav" type="button" disabled={!canNavigateFrames} onClick={() => selectNeighborFrame(1)}>
                {t("sequence.editor.nextFrame")}
              </button>
            </>
          }
        >
          <div className="sequence-canvas">
            {showOnionSkin && previousUrl ? <img className="onion-frame previous" src={previousUrl} alt="" aria-hidden="true" /> : null}
            {activeUrl ? <img className="active-frame" src={activeUrl} alt={activeFrame?.original_name ?? t("sequence.editor.currentFrame")} /> : <span>{t("sequence.editor.loadingFrame")}</span>}
            {showOnionSkin && nextUrl ? <img className="onion-frame next" src={nextUrl} alt="" aria-hidden="true" /> : null}
            {showDifferenceMap && differenceMap.url ? <img className="difference-map" src={differenceMap.url} alt={t("sequence.editor.differenceMapAlt")} /> : null}
            <div className="anchor-line horizontal" />
            <div className="anchor-line vertical" />
          </div>
        </WorkbenchPreview>
      </section>

      <aside className="settings-panel sequence-settings">
        <h2>{t("sequence.editor.settings")}</h2>
        <div className="sequence-toggle-group" aria-label={t("sequence.editor.previewControls")}>
          <button className="ghost compact" type="button" onClick={() => setPlaying((current) => !current)}>
            {playing ? <Pause size={16} /> : <Play size={16} />}
            {playing ? t("sequence.editor.pause") : t("sequence.editor.play")}
          </button>
          <button
            className={`ghost compact ${showOnionSkin ? "active-soft" : ""}`}
            type="button"
            aria-pressed={showOnionSkin}
            onClick={() => setShowOnionSkin((current) => !current)}
          >
            {t("sequence.editor.onionSkin")}
          </button>
          <button className="ghost compact" type="button" disabled={!activeFrame} onClick={lockReferenceFrame}>
            {t("sequence.editor.lockReference")}
          </button>
          <button
            className={`ghost compact ${showDifferenceMap ? "active-soft" : ""}`}
            type="button"
            disabled={!referenceFrame || !activeFrame}
            aria-pressed={showDifferenceMap}
            onClick={() => setShowDifferenceMap((current) => !current)}
          >
            {t("sequence.editor.differenceMap")}
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
          {t("sequence.editor.editFrame")}
        </button>
        <label className="number-field">
          <span>{t("sequence.editor.currentSequence")}</span>
          <select value={sequence.id} title={sequence.name} onChange={(event) => void onSelect(event.target.value)}>
            {sequences.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label className="number-field">
          <span>{t("sequence.editor.name")}</span>
          <input value={draftSequence.name} title={draftSequence.name} onChange={(event) => setDraftSequence({ ...draftSequence, name: event.target.value })} />
        </label>
        <NumberField label={t("sequence.editor.fps")} value={draftSequence.fps} min={1} max={60} onChange={(fps) => setDraftSequence({ ...draftSequence, fps })} />
        <NumberField
          label={t("sequence.editor.canvasWidth")}
          value={draftSequence.canvas_width}
          min={0}
          max={4096}
          onChange={(canvas_width) => setDraftSequence({ ...draftSequence, canvas_width })}
        />
        <NumberField
          label={t("sequence.editor.canvasHeight")}
          value={draftSequence.canvas_height}
          min={0}
          max={4096}
          onChange={(canvas_height) => setDraftSequence({ ...draftSequence, canvas_height })}
        />
        <label className="setting-check">
          <input type="checkbox" checked={draftSequence.loop} onChange={(event) => setDraftSequence({ ...draftSequence, loop: event.target.checked })} />
          {t("sequence.editor.loop")}
        </label>
        <label className="number-field">
          <span>{t("sequence.editor.anchorMode")}</span>
          <select value={draftSequence.anchor_mode} onChange={(event) => setDraftSequence({ ...draftSequence, anchor_mode: event.target.value })}>
            <option value="bottom_center">{t("sequence.editor.bottomCenter")}</option>
            <option value="center">{t("sequence.editor.canvasCenter")}</option>
          </select>
        </label>

        <h2>{t("sequence.editor.cleanup")}</h2>
        <NumberField label={t("sequence.editor.alphaThreshold")} value={params.alpha_threshold} min={0} max={255} onChange={(value) => onParamsChange((current) => ({ ...current, alpha_threshold: value }))} />
        <NumberField label={t("sequence.editor.alphaSmoothing")} value={params.alpha_smoothing} min={0} max={10} onChange={(value) => onParamsChange((current) => ({ ...current, alpha_smoothing: value }))} />
        <NumberField label={t("sequence.editor.trimPadding")} value={params.trim_padding} min={0} max={80} onChange={(value) => onParamsChange((current) => ({ ...current, trim_padding: value }))} />
        <NumberField label={t("sequence.editor.canvasPadding")} value={params.canvas_padding} min={0} max={120} onChange={(value) => onParamsChange((current) => ({ ...current, canvas_padding: value }))} />
        <label className="setting-check">
          <input type="checkbox" checked={params.denoise} onChange={(event) => onParamsChange((current) => ({ ...current, denoise: event.target.checked }))} />
          {t("sequence.editor.denoise")}
        </label>
        <h2>{t("sequence.editor.consistency")}</h2>
        <label className="setting-check">
          <input type="checkbox" checked={params.color_match} onChange={(event) => onParamsChange((current) => ({ ...current, color_match: event.target.checked }))} />
          {t("sequence.editor.colorMatch")}
        </label>
        <label className="setting-check">
          <input type="checkbox" checked={params.stabilize} onChange={(event) => onParamsChange((current) => ({ ...current, stabilize: event.target.checked }))} />
          {t("sequence.editor.stabilize")}
        </label>
        <NumberField
          label={t("sequence.editor.stabilizeStrength")}
          value={params.stabilize_strength}
          min={0}
          max={100}
          onChange={(value) => onParamsChange((current) => ({ ...current, stabilize_strength: value }))}
        />
        <p className="helper-text">{t("sequence.editor.referenceFrame", { frame: referenceFrame ? `${referenceFrame.frame_index + 1} · ${referenceFrame.original_name}` : t("sequence.editor.notLocked") })}</p>
        <button className="primary install-button" type="button" disabled={!canWrite} onClick={() => void onSaveSettings(draftSequence, params)}>
          {t("sequence.editor.saveSettings")}
        </button>
        <div className="export-stack">
          <button className="ghost danger-text" type="button" disabled={!canWrite} onClick={() => void onDelete(sequence.id)}>
            {t("sequence.editor.deleteSequence")}
          </button>
        </div>

        <SequenceDiagnosticsPanel diagnostics={diagnostics} referenceFrame={referenceFrame} differenceMap={differenceMap} />

        <div className="timeline-strip">
          {frames.map((frame) => (
            <button
              key={frame.id}
              className={`frame-thumb ${frame.id === activeFrame?.id ? "active" : ""} ${frame.id === referenceFrame?.id ? "reference" : ""} ${frame.enabled ? "" : "disabled"}`}
              type="button"
              onClick={() => setActiveFrameId(frame.id)}
            >
              <SequenceFrameThumb frame={frame} />
              <span>{frame.frame_index + 1}</span>
            </button>
          ))}
        </div>

        {activeFrame ? (
          <div className="frame-editor">
            <strong>{activeFrame.original_name}</strong>
            <button className="ghost compact" type="button" onClick={() => reorderFrame(activeFrame.id, -1)}>
              {t("sequence.editor.moveEarlier")}
            </button>
            <button className="ghost compact" type="button" onClick={() => reorderFrame(activeFrame.id, 1)}>
              {t("sequence.editor.moveLater")}
            </button>
            <button className="ghost compact" type="button" onClick={() => updateFrame(activeFrame.id, { enabled: !activeFrame.enabled })}>
              {activeFrame.enabled ? t("sequence.editor.disableFrame") : t("sequence.editor.enableFrame")}
            </button>
            <label>
              {t("sequence.editor.xOffset")}
              <input type="number" value={activeFrame.offset_x} onChange={(event) => updateFrame(activeFrame.id, { offset_x: Number(event.target.value) })} />
            </label>
            <label>
              {t("sequence.editor.yOffset")}
              <input type="number" value={activeFrame.offset_y} onChange={(event) => updateFrame(activeFrame.id, { offset_y: Number(event.target.value) })} />
            </label>
            <button className="primary compact" type="button" disabled={!canWrite} onClick={() => void onSaveFrames(draftFrames)}>
              {t("sequence.editor.saveFrameChanges")}
            </button>
          </div>
        ) : null}
        {error ? <p className="error-text">{error}</p> : null}
      </aside>
    </>
  );
}

function SequenceFrameThumb({ frame }: { frame: SequenceFrameResponse }) {
  const url = useObjectUrl(frame.preview_url);
  return url ? <img src={url} alt={frame.original_name} /> : <em />;
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
  const { t } = useTranslation("workflows");
  return (
    <div className="sequence-diagnostics">
      <div className="diagnostics-heading">
        <div>
          <strong>{t("sequence.diagnostics.title")}</strong>
          <span>{referenceFrame ? t("sequence.diagnostics.referenceFrame", { frame: referenceFrame.frame_index + 1 }) : t("sequence.diagnostics.noReference")}</span>
        </div>
        <span className={`diff-status ${differenceMap.status}`}>{differenceMap.status === "loading" ? t("sequence.diagnostics.analyzing") : differenceMap.status === "ready" ? t("sequence.diagnostics.ready") : t("sequence.diagnostics.local")}</span>
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
    image.onerror = () => reject(new Error("Could not read image."));
    image.src = url;
  });
}

function drawAlignedImage(image: HTMLImageElement, width: number, height: number) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (context) {
    // Bottom-center alignment matches the default character anchor and emphasizes subject drift over canvas size.
    context.drawImage(image, Math.round((width - image.naturalWidth) / 2), height - image.naturalHeight);
  }
  return canvas;
}

function readSequenceDiagnostics(
  frames: SequenceFrameResponse[],
  referenceFrame: SequenceFrameResponse | null,
  activeFrame: SequenceFrameResponse | null,
  differenceMap: FrameDifferenceMap,
  t: TFunction,
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
    notes.push({ tone: "warn", title: t("sequence.diagnostics.referenceTitle"), detail: t("sequence.diagnostics.referenceDetail") });
  }
  if (enabledFrames.length < 8) {
    notes.push({ tone: "warn", title: t("sequence.diagnostics.keyStages"), detail: t("sequence.diagnostics.fewFrames") });
  } else {
    notes.push({ tone: "ok", title: t("sequence.diagnostics.keyStages"), detail: t("sequence.diagnostics.enoughFrames") });
  }
  if (widthJitter > 8 || heightJitter > 6) {
    notes.push({ tone: "warn", title: t("sequence.diagnostics.outlineDrift"), detail: t("sequence.diagnostics.outlineDetail") });
  }
  if (baselineJitter > 3) {
    notes.push({ tone: "warn", title: t("sequence.diagnostics.baseline"), detail: t("sequence.diagnostics.baselineDetail") });
  }
  if (differenceMap.status === "ready" && activeFrame && referenceFrame && activeFrame.id !== referenceFrame.id) {
    const tone = differenceMap.score > 18 || differenceMap.changedPct > 30 ? "danger" : differenceMap.score > 10 ? "warn" : "ok";
    notes.push({
      tone,
      title: t("sequence.diagnostics.currentDifference"),
      detail: t("sequence.diagnostics.differenceDetail", { score: differenceMap.score.toFixed(1), changed: differenceMap.changedPct.toFixed(1) }),
    });
  }

  return {
    metrics: [
      { label: t("sequence.diagnostics.sizeDrift"), value: `${widthJitter}×${heightJitter}px` },
      { label: t("sequence.diagnostics.baselineDrift"), value: `${baselineJitter}px` },
      { label: t("sequence.diagnostics.currentDifference"), value: differenceMap.status === "ready" ? differenceMap.score.toFixed(1) : "-" },
    ],
    notes,
  };
}

function readRange(values: number[]) {
  if (!values.length) return 0;
  return Math.max(...values) - Math.min(...values);
}

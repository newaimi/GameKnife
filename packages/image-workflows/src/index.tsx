import { useEffect, useMemo, useRef, useState, type PointerEvent, type ReactNode } from "react";
import { Bone, Brush, Download, Eraser, Play, RefreshCw, Save, Trash2, UploadCloud, Volume2 } from "lucide-react";
import { gameKnifeApiClient } from "@gameknife/api-client";
import { createManualEditDocument, drawBlobToCanvas, drawBrushStroke, exportCanvasAsPngBlob, readCanvasPoint, type BrushMode, type EditorDocument } from "@gameknife/editor-core";
import type { AssetResponse, CharacterPartResponse, CharacterRigResponse, JobResponse, OutputAssetRef, SequenceResponse, VideoGenerationConfig } from "@gameknife/shared-types";
import { NumberField, WorkbenchPreview } from "@gameknife/ui-kit";

export const communityToolEntries = [
  { id: "background-remove", label: "去背景", route: "/tools/background-remove" },
  { id: "upscale", label: "图片放大", route: "/tools/upscale" },
  { id: "asset-board", label: "素材板", route: "/tools/asset-board" },
  { id: "sequence", label: "序列帧", route: "/tools/sequence" },
  { id: "video-generate", label: "AI生成视频", route: "/tools/video-generate" },
  { id: "video-to-sequence", label: "视频转帧", route: "/tools/video-to-sequence" },
  { id: "character-rig", label: "骨骼拆分", route: "/tools/character-rig" },
  { id: "sound-effect", label: "声效生成", route: "/tools/sound-effect" },
  { id: "manual-edit", label: "手动编辑", route: "/manual-edit" },
];

export function CommunityToolHome() {
  return (
    <div className="tool-home">
      {communityToolEntries.map((tool) => (
        <a className="tool-entry" href={tool.route} key={tool.id}>
          {tool.label}
        </a>
      ))}
      <WorkbenchPreview />
    </div>
  );
}

export function UpscaleWorkspace() {
  const [asset, setAsset] = useState<AssetResponse | null>(null);
  const [scale, setScale] = useState(2);
  const [job, setJob] = useState<JobResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function upload(file: File) {
    setError("");
    setAsset(await gameKnifeApiClient.uploadImage(file));
    setJob(null);
  }

  async function run() {
    if (!asset) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const created = await gameKnifeApiClient.createUpscaleJob(asset.id, { style: "pixel", scale });
      setJob(await waitForJob(created.id));
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setBusy(false);
    }
  }

  return (
    <ToolLayout
      title="图片放大"
      left={<ImageUploadBox onFile={upload} />}
      center={<AssetPreview asset={asset} />}
      right={
        <div className="tool-panel">
          <NumberField label="倍率" value={scale} min={2} max={8} step={2} onChange={setScale} />
          <button className="primary-button" disabled={!asset || busy} onClick={run} type="button">
            <Play size={18} />
            放大
          </button>
          <StatusLine error={error} job={job} />
        </div>
      }
      results={<JobResult job={job} />}
    />
  );
}

export function AssetBoardWorkspace() {
  const [asset, setAsset] = useState<AssetResponse | null>(null);
  const [job, setJob] = useState<JobResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function upload(file: File) {
    setError("");
    setAsset(await gameKnifeApiClient.uploadImage(file));
    setJob(null);
  }

  async function detectRegions() {
    if (!asset) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const created = await gameKnifeApiClient.createAssetBoardRegionJob(asset.id, { min_component_area: 8, alpha_threshold: 16 });
      setJob(await waitForJob(created.id));
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setBusy(false);
    }
  }

  const components = Array.isArray(job?.result.components) ? (job.result.components as Array<Record<string, unknown>>) : [];

  return (
    <ToolLayout
      title="素材板"
      left={<ImageUploadBox onFile={upload} />}
      center={<AssetPreview asset={asset} />}
      right={
        <div className="tool-panel">
          <button className="primary-button" disabled={!asset || busy} onClick={detectRegions} type="button">
            <RefreshCw size={18} />
            识别区域
          </button>
          <StatusLine error={error} job={job} />
          <div className="mini-list">
            {components.map((component) => (
              <span key={String(component.id)}>
                #{String(component.id)} {formatBbox(component.bbox)}
              </span>
            ))}
          </div>
        </div>
      }
      results={<JobResult job={job} />}
    />
  );
}

export function SequenceWorkspace() {
  const [sequence, setSequence] = useState<SequenceResponse | null>(null);
  const [sequences, setSequences] = useState<SequenceResponse[]>([]);
  const [fps, setFps] = useState(12);
  const [name, setName] = useState("sequence");
  const [job, setJob] = useState<JobResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    void refreshSequences();
  }, []);

  async function refreshSequences() {
    setSequences(await gameKnifeApiClient.listSequences());
  }

  async function importFrames(files: FileList | null) {
    if (!files?.length) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const imported = await gameKnifeApiClient.uploadSequenceFrames(Array.from(files), name, fps);
      setSequence(imported);
      setJob(null);
      await refreshSequences();
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setBusy(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  }

  async function runJob(kind: "clean" | "frames" | "spine") {
    if (!sequence) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const created =
        kind === "clean"
          ? await gameKnifeApiClient.createSequenceCleanJob(sequence.id, {})
          : kind === "frames"
            ? await gameKnifeApiClient.createSequenceFramesExportJob(sequence.id, {})
            : await gameKnifeApiClient.createSequenceSpineExportJob(sequence.id, {});
      const finished = await waitForJob(created.id);
      setJob(finished);
      setSequence(await gameKnifeApiClient.getSequence(sequence.id));
      await refreshSequences();
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setBusy(false);
    }
  }

  const previewFrame = sequence?.frames[0] ?? null;

  return (
    <ToolLayout
      title="序列帧"
      left={
        <div className="tool-panel">
          <label className="field-label">
            名称
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <NumberField label="FPS" value={fps} min={1} max={60} onChange={setFps} />
          <input accept="image/*" multiple onChange={(event) => importFrames(event.target.files)} ref={fileInputRef} type="file" />
          <button className="secondary-button" disabled={busy} onClick={() => fileInputRef.current?.click()} type="button">
            <UploadCloud size={18} />
            导入
          </button>
          <div className="mini-list">
            {sequences.map((item) => (
              <button key={item.id} onClick={() => gameKnifeApiClient.getSequence(item.id).then(setSequence).catch((exc) => setError(readMessage(exc)))} type="button">
                {item.name}
              </button>
            ))}
          </div>
        </div>
      }
      center={<RemoteImagePreview title={previewFrame?.original_name ?? ""} url={previewFrame?.preview_url ?? ""} />}
      right={
        <div className="tool-panel">
          <button className="primary-button" disabled={!sequence || busy} onClick={() => runJob("clean")} type="button">
            <RefreshCw size={18} />
            清洗
          </button>
          <button className="secondary-button" disabled={!sequence || busy} onClick={() => runJob("frames")} type="button">
            <Download size={18} />
            PNG 包
          </button>
          <button className="secondary-button" disabled={!sequence || busy} onClick={() => runJob("spine")} type="button">
            <Download size={18} />
            Spine
          </button>
          <StatusLine error={error} job={job} />
          {sequence ? <span>{sequence.frame_count} 帧</span> : null}
        </div>
      }
      results={<JobResult job={job} />}
    />
  );
}

export function VideoToSequenceWorkspace() {
  const [videoAsset, setVideoAsset] = useState<AssetResponse | null>(null);
  const [sequence, setSequence] = useState<SequenceResponse | null>(null);
  const [name, setName] = useState("video-sequence");
  const [fps, setFps] = useState(12);
  const [maxFrames, setMaxFrames] = useState(48);
  const [job, setJob] = useState<JobResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function upload(file: File) {
    setBusy(true);
    setError("");
    try {
      const uploaded = await gameKnifeApiClient.uploadVideo(file);
      setVideoAsset(uploaded);
      setSequence(null);
      setJob(null);
      setName(file.name.replace(/\.[^.]+$/, "") || "video-sequence");
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setBusy(false);
    }
  }

  async function extract() {
    if (!videoAsset) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const created = await gameKnifeApiClient.createSequenceFromVideoJob({
        video_asset_id: videoAsset.id,
        name,
        fps,
        max_frames: maxFrames,
        remove_background: false,
      });
      const finished = await waitForJob(created.id);
      setJob(finished);
      const sequenceId = typeof finished.result.sequence_id === "string" ? finished.result.sequence_id : "";
      if (sequenceId) {
        setSequence(await gameKnifeApiClient.getSequence(sequenceId));
      }
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setBusy(false);
    }
  }

  const previewFrame = sequence?.frames[0] ?? null;

  return (
    <ToolLayout
      title="视频转帧"
      left={
        <div className="tool-panel">
          <label className="field-label">
            名称
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <VideoUploadBox onFile={upload} />
          {videoAsset ? <span>{videoAsset.filename}</span> : null}
        </div>
      }
      center={<RemoteImagePreview title={previewFrame?.original_name ?? ""} url={previewFrame?.preview_url ?? ""} />}
      right={
        <div className="tool-panel">
          <NumberField label="FPS" value={fps} min={1} max={60} onChange={setFps} />
          <NumberField label="帧数" value={maxFrames} min={1} max={300} onChange={setMaxFrames} />
          <button className="primary-button" disabled={!videoAsset || busy} onClick={extract} type="button">
            <Play size={18} />
            抽帧
          </button>
          <StatusLine error={error} job={job} />
          {sequence ? <span>{sequence.frame_count} 帧</span> : null}
        </div>
      }
      results={<JobResult job={job} />}
    />
  );
}

export function VideoGenerateWorkspace() {
  const [asset, setAsset] = useState<AssetResponse | null>(null);
  const [action, setAction] = useState("walk_down");
  const [prompt, setPrompt] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [duration, setDuration] = useState(5);
  const [resolution, setResolution] = useState("720P");
  const [confirmed, setConfirmed] = useState(false);
  const [job, setJob] = useState<JobResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function upload(file: File) {
    setBusy(true);
    setError("");
    try {
      setAsset(await gameKnifeApiClient.uploadImage(file));
      setJob(null);
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setBusy(false);
    }
  }

  async function run() {
    if (!asset) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const created = await gameKnifeApiClient.createVideoGenerationJob({
        input_asset_id: asset.id,
        action,
        prompt,
        negative_prompt: negativePrompt,
        duration,
        resolution,
        confirmed_external_api: confirmed,
      });
      setJob(await waitForJob(created.id, 30, 1000));
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setBusy(false);
    }
  }

  return (
    <ToolLayout
      title="AI生成视频"
      left={<ImageUploadBox onFile={upload} />}
      center={<AssetPreview asset={asset} />}
      right={
        <div className="tool-panel">
          <label className="field-label">
            动作
            <input value={action} onChange={(event) => setAction(event.target.value)} />
          </label>
          <label className="field-label">
            提示词
            <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={4} />
          </label>
          <label className="field-label">
            负向词
            <textarea value={negativePrompt} onChange={(event) => setNegativePrompt(event.target.value)} rows={3} />
          </label>
          <NumberField label="时长" value={duration} min={2} max={15} step={1} onChange={setDuration} />
          <label className="field-label">
            分辨率
            <select value={resolution} onChange={(event) => setResolution(event.target.value)}>
              <option value="480P">480P</option>
              <option value="720P">720P</option>
              <option value="1080P">1080P</option>
            </select>
          </label>
          <label className="check-row">
            <input checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} type="checkbox" />
            确认调用外部 API
          </label>
          <button className="primary-button" disabled={!asset || busy} onClick={run} type="button">
            <Play size={18} />
            生成
          </button>
          <StatusLine error={error} job={job} />
        </div>
      }
      results={<JobResult job={job} />}
    />
  );
}

export function SoundEffectWorkspace() {
  const [prompt, setPrompt] = useState("coin pickup");
  const [durationSeconds, setDurationSeconds] = useState(4);
  const [steps, setSteps] = useState(100);
  const [cfgScale, setCfgScale] = useState(7);
  const [seed, setSeed] = useState(-1);
  const [job, setJob] = useState<JobResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function run() {
    const trimmedPrompt = prompt.trim();
    if (!trimmedPrompt) {
      setError("请输入声效提示词。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const created = await gameKnifeApiClient.createSoundEffectJob({
        prompt: trimmedPrompt,
        duration_seconds: durationSeconds,
        seed,
        steps,
        cfg_scale: cfgScale,
      });
      setJob(await waitForJob(created.id));
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setBusy(false);
    }
  }

  return (
    <ToolLayout
      title="声效生成"
      left={
        <div className="tool-panel">
          <label className="field-label">
            提示词
            <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={7} />
          </label>
        </div>
      }
      center={<WorkbenchPreview emptyLabel="暂无声效" />}
      right={
        <div className="tool-panel">
          <NumberField label="时长" value={durationSeconds} min={1} max={30} step={1} onChange={setDurationSeconds} />
          <NumberField label="步数" value={steps} min={10} max={250} step={10} onChange={setSteps} />
          <NumberField label="CFG" value={cfgScale} min={1} max={20} step={0.5} onChange={setCfgScale} />
          <NumberField label="种子" value={seed} min={-1} max={2147483647} step={1} onChange={setSeed} />
          <button className="primary-button" disabled={busy} onClick={run} type="button">
            <Volume2 size={18} />
            生成
          </button>
          <StatusLine error={error} job={job} />
        </div>
      }
      results={<JobResult job={job} />}
    />
  );
}

export function CharacterRigWorkspace() {
  const [rig, setRig] = useState<CharacterRigResponse | null>(null);
  const [rigs, setRigs] = useState<CharacterRigResponse[]>([]);
  const [name, setName] = useState("character");
  const [minArea, setMinArea] = useState(12);
  const [padding, setPadding] = useState(2);
  const [job, setJob] = useState<JobResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    void refreshRigs();
  }, []);

  async function refreshRigs() {
    setRigs(await gameKnifeApiClient.listCharacterRigs());
  }

  async function importRig(file: File) {
    setBusy(true);
    setError("");
    try {
      const imported = await gameKnifeApiClient.importCharacterRig(file, name);
      setRig(imported);
      setJob(null);
      await refreshRigs();
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setBusy(false);
    }
  }

  async function selectRig(rigId: string) {
    try {
      setError("");
      setRig(await gameKnifeApiClient.getCharacterRig(rigId));
      setJob(null);
    } catch (exc) {
      setError(readMessage(exc));
    }
  }

  async function runAnalyze() {
    if (!rig) {
      return;
    }
    await runRigJob(() => gameKnifeApiClient.createCharacterRigAnalyzeJob(rig.id, { min_component_area: minArea, padding, alpha_threshold: 16 }), true);
  }

  async function runExport(kind: "spine" | "dragonbones") {
    if (!rig) {
      return;
    }
    await runRigJob(
      () =>
        kind === "spine"
          ? gameKnifeApiClient.createCharacterRigSpineExportJob(rig.id, {})
          : gameKnifeApiClient.createCharacterRigDragonBonesExportJob(rig.id, {}),
      false,
    );
  }

  async function refinePart(part: CharacterPartResponse) {
    if (!rig) {
      return;
    }
    await runRigJob(() => gameKnifeApiClient.createCharacterPartRefineJob(rig.id, part.id, { padding }), true);
  }

  async function removeRig() {
    if (!rig) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      await gameKnifeApiClient.deleteCharacterRig(rig.id);
      setRig(null);
      setJob(null);
      await refreshRigs();
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setBusy(false);
    }
  }

  async function runRigJob(create: () => Promise<JobResponse>, refreshRig: boolean) {
    if (!rig) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const created = await create();
      const finished = await waitForJob(created.id);
      setJob(finished);
      if (refreshRig) {
        setRig(await gameKnifeApiClient.getCharacterRig(rig.id));
        await refreshRigs();
      }
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setBusy(false);
    }
  }

  return (
    <ToolLayout
      title="骨骼拆分"
      left={
        <div className="tool-panel">
          <label className="field-label">
            名称
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <ImageUploadBox onFile={importRig} />
          <div className="mini-list">
            {rigs.map((item) => (
              <button key={item.id} onClick={() => selectRig(item.id)} type="button">
                {item.name}
              </button>
            ))}
          </div>
        </div>
      }
      center={<RemoteImagePreview title={rig?.name ?? ""} url={rig?.source_url ?? ""} />}
      right={
        <div className="tool-panel">
          <NumberField label="面积" value={minArea} min={1} max={4096} step={1} onChange={setMinArea} />
          <NumberField label="留边" value={padding} min={0} max={32} step={1} onChange={setPadding} />
          <button className="primary-button" disabled={!rig || busy} onClick={runAnalyze} type="button">
            <Bone size={18} />
            分析
          </button>
          <button className="secondary-button" disabled={!rig || !rig.part_count || busy} onClick={() => runExport("spine")} type="button">
            <Download size={18} />
            Spine
          </button>
          <button className="secondary-button" disabled={!rig || !rig.part_count || busy} onClick={() => runExport("dragonbones")} type="button">
            <Download size={18} />
            DragonBones
          </button>
          <button className="secondary-button" disabled={!rig || busy} onClick={removeRig} type="button">
            <Trash2 size={18} />
            删除
          </button>
          <StatusLine error={error} job={job} />
          {rig ? <span>{rig.part_count} 个部件</span> : null}
        </div>
      }
      results={
        <>
          <JobResult job={job} />
          <CharacterPartList busy={busy} parts={rig?.parts ?? []} onRefine={refinePart} />
        </>
      }
    />
  );
}

export function ManualEditWorkspace() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawingRef = useRef(false);
  const [sourceAsset, setSourceAsset] = useState<AssetResponse | null>(null);
  const [savedAsset, setSavedAsset] = useState<AssetResponse | null>(null);
  const [document, setDocument] = useState<EditorDocument | null>(null);
  const [mode, setMode] = useState<BrushMode>("paint");
  const [brushSize, setBrushSize] = useState(12);
  const [brushColor, setBrushColor] = useState("#ff365f");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function upload(file: File) {
    setBusy(true);
    setError("");
    setSavedAsset(null);
    try {
      const uploaded = await gameKnifeApiClient.uploadImage(file);
      const blob = await gameKnifeApiClient.requestBlob(uploaded.url);
      const canvas = requireManualEditCanvas(canvasRef.current);
      const size = await drawBlobToCanvas(canvas, blob);
      setSourceAsset(uploaded);
      setDocument(createManualEditDocument(uploaded.id, uploaded.filename, size, uploaded.id));
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setBusy(false);
    }
  }

  function draw(event: PointerEvent<HTMLCanvasElement>) {
    if (!document) {
      return;
    }
    const canvas = requireManualEditCanvas(canvasRef.current);
    drawBrushStroke(canvas, readCanvasPoint(canvas, event.clientX, event.clientY), {
      mode,
      size: brushSize,
      color: brushColor,
    });
  }

  function startDrawing(event: PointerEvent<HTMLCanvasElement>) {
    drawingRef.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
    draw(event);
  }

  function moveDrawing(event: PointerEvent<HTMLCanvasElement>) {
    if (drawingRef.current) {
      draw(event);
    }
  }

  function stopDrawing() {
    drawingRef.current = false;
  }

  async function save() {
    if (!document || !sourceAsset) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const canvas = requireManualEditCanvas(canvasRef.current);
      const blob = await exportCanvasAsPngBlob(canvas);
      const filename = manualEditFilename(document.name);
      const file = new File([blob], filename, { type: "image/png" });
      setSavedAsset(await gameKnifeApiClient.saveManualEditAsset(file, filename, sourceAsset.id, "manual-edit"));
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="manual-edit-page">
      <h1>手动编辑</h1>
      <div className="manual-edit-shell">
        <aside className="tool-panel">
          <ImageUploadBox onFile={upload} />
          <div className="segmented-controls">
            <button className={`secondary-button ${mode === "paint" ? "is-active" : ""}`} onClick={() => setMode("paint")} type="button">
              <Brush size={18} />
              画笔
            </button>
            <button className={`secondary-button ${mode === "erase" ? "is-active" : ""}`} onClick={() => setMode("erase")} type="button">
              <Eraser size={18} />
              橡皮
            </button>
          </div>
          <NumberField label="笔刷" value={brushSize} min={1} max={96} step={1} onChange={setBrushSize} />
          <label className="field-label">
            颜色
            <input value={brushColor} onChange={(event) => setBrushColor(event.target.value)} type="color" />
          </label>
        </aside>
        <section className="manual-edit-stage">
          <WorkbenchPreview emptyLabel="暂无素材">
            {document ? null : <span>暂无素材</span>}
            <canvas
              className={`manual-edit-canvas ${document ? "" : "is-empty"}`}
              onPointerCancel={stopDrawing}
              onPointerDown={startDrawing}
              onPointerLeave={stopDrawing}
              onPointerMove={moveDrawing}
              onPointerUp={stopDrawing}
              ref={canvasRef}
            />
          </WorkbenchPreview>
        </section>
        <aside className="tool-panel">
          <button className="primary-button" disabled={!document || busy} onClick={save} type="button">
            <Save size={18} />
            保存
          </button>
          <StatusLine error={error} job={null} />
          <AssetSaveResult asset={savedAsset} />
        </aside>
      </div>
    </section>
  );
}

function CharacterPartList({ busy, parts, onRefine }: { busy: boolean; parts: CharacterPartResponse[]; onRefine: (part: CharacterPartResponse) => void }) {
  if (!parts.length) {
    return null;
  }
  return (
    <div className="mini-list">
      {parts.map((part) => (
        <div className="part-row" key={part.id}>
          <span>
            {part.name} {formatBbox(part.bbox)}
          </span>
          <button className="secondary-button" disabled={busy} onClick={() => onRefine(part)} type="button">
            <RefreshCw size={18} />
            精修
          </button>
        </div>
      ))}
    </div>
  );
}

export function CommunityJobsPage() {
  const [jobs, setJobs] = useState<JobResponse[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    void refresh();
  }, []);

  async function refresh() {
    try {
      setError("");
      setJobs(await gameKnifeApiClient.listJobs());
    } catch (exc) {
      setError(readMessage(exc));
    }
  }

  async function remove(jobId: string) {
    try {
      await gameKnifeApiClient.deleteJob(jobId);
      await refresh();
    } catch (exc) {
      setError(readMessage(exc));
    }
  }

  return (
    <section className="page-panel">
      <div className="page-actions">
        <h1>任务</h1>
        <button className="secondary-button" onClick={refresh} type="button">
          <RefreshCw size={18} />
          刷新
        </button>
      </div>
      {error ? <p className="error-text">{error}</p> : null}
      <div className="job-list">
        {jobs.map((job) => (
          <article className="job-card" key={job.id}>
            <strong>{job.type}</strong>
            <span>{job.status}</span>
            <span>{job.input_filename ?? job.input_asset_id}</span>
            <JobResult job={job} />
            {job.status !== "pending" && job.status !== "running" ? (
              <button className="icon-button" onClick={() => remove(job.id)} title="删除" type="button">
                <Trash2 size={18} />
              </button>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

export function CommunitySettingsPage() {
  const [settings, setSettings] = useState<Record<string, unknown> | null>(null);
  const [videoConfig, setVideoConfig] = useState<VideoGenerationConfig | null>(null);
  const [videoProvider, setVideoProvider] = useState<VideoGenerationConfig["provider"]>("aliyun_dashscope");
  const [videoBaseUrl, setVideoBaseUrl] = useState("");
  const [videoApiKey, setVideoApiKey] = useState("");
  const [videoMessage, setVideoMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    void refreshSettings();
  }, []);

  async function refreshSettings() {
    try {
      setError("");
      const [nextSettings, nextVideoConfig] = await Promise.all([gameKnifeApiClient.getSettings(), gameKnifeApiClient.getVideoGenerationSettings()]);
      setSettings(nextSettings);
      setVideoConfig(nextVideoConfig);
      setVideoProvider(nextVideoConfig.provider);
      setVideoBaseUrl(nextVideoConfig.base_url);
      setVideoApiKey("");
    } catch (exc) {
      setError(readMessage(exc));
    }
  }

  async function saveVideoConfig() {
    try {
      setError("");
      setVideoMessage("");
      const payload = { provider: videoProvider, base_url: videoBaseUrl, ...(videoApiKey ? { api_key: videoApiKey } : {}) };
      const saved = await gameKnifeApiClient.updateVideoGenerationSettings(payload);
      setVideoConfig(saved);
      setVideoApiKey("");
      setVideoMessage("已保存");
    } catch (exc) {
      setError(readMessage(exc));
    }
  }

  async function testVideoConfig() {
    try {
      setError("");
      setVideoMessage("");
      const result = await gameKnifeApiClient.testVideoGenerationSettings({
        provider: videoProvider,
        base_url: videoBaseUrl,
        ...(videoApiKey ? { api_key: videoApiKey } : {}),
      });
      setVideoMessage(String(result.message ?? "ok"));
    } catch (exc) {
      setError(readMessage(exc));
    }
  }

  return (
    <section className="page-panel">
      <h1>设置</h1>
      {error ? <p className="error-text">{error}</p> : null}
      <div className="settings-grid">
        <span>版本</span>
        <strong>{String(settings?.edition ?? "")}</strong>
        <span>工作区</span>
        <strong>{String(settings?.workspace_id ?? "")}</strong>
        <span>存储</span>
        <strong>{String(settings?.storage ?? "")}</strong>
      </div>
      <div className="settings-form">
        <h2>视频生成 API</h2>
        <label className="field-label">
          供应商
          <select value={videoProvider} onChange={(event) => setVideoProvider(event.target.value as VideoGenerationConfig["provider"])}>
            <option value="aliyun_dashscope">阿里云 DashScope</option>
            <option value="seedance">Seedance</option>
          </select>
        </label>
        <label className="field-label">
          Base URL
          <input value={videoBaseUrl} onChange={(event) => setVideoBaseUrl(event.target.value)} />
        </label>
        <label className="field-label">
          API Key
          <input placeholder={videoConfig?.masked_api_key ?? ""} value={videoApiKey} onChange={(event) => setVideoApiKey(event.target.value)} />
        </label>
        <div className="job-result">
          <button className="primary-button" onClick={saveVideoConfig} type="button">
            <Save size={18} />
            保存
          </button>
          <button className="secondary-button" onClick={testVideoConfig} type="button">
            <RefreshCw size={18} />
            测试
          </button>
          {videoMessage ? <span className="status-text">{videoMessage}</span> : null}
        </div>
      </div>
    </section>
  );
}

export function CommunityHelpPage() {
  return (
    <section className="page-panel">
      <h1>帮助</h1>
      <div className="mini-list">
        {communityToolEntries.map((tool) => (
          <a href={tool.route} key={tool.id}>
            {tool.label}
          </a>
        ))}
      </div>
    </section>
  );
}

export function ModelRequiredWorkspace({ title }: { title: string }) {
  const [error, setError] = useState("");
  return (
    <ToolLayout
      title={title}
      left={<div className="tool-panel" />}
      center={<WorkbenchPreview />}
      right={
        <div className="tool-panel">
          <button className="primary-button" onClick={() => setError("当前不可用。")} type="button">
            <Play size={18} />
            启动
          </button>
          {error ? <p className="error-text">{error}</p> : null}
        </div>
      }
    />
  );
}

function ToolLayout({ title, left, center, right, results }: { title: string; left: ReactNode; center: ReactNode; right: ReactNode; results?: ReactNode }) {
  return (
    <section className="workflow-page">
      <h1>{title}</h1>
      <div className="workflow-grid">
        {left}
        {center}
        {right}
      </div>
      {results ? <div className="result-panel">{results}</div> : null}
    </section>
  );
}

function ImageUploadBox({ onFile }: { onFile: (file: File) => void }) {
  return (
    <label className="upload-box">
      <UploadCloud size={22} />
      上传
      <input accept="image/*" onChange={(event) => event.target.files?.[0] && onFile(event.target.files[0])} type="file" />
    </label>
  );
}

function VideoUploadBox({ onFile }: { onFile: (file: File) => void }) {
  return (
    <label className="upload-box">
      <UploadCloud size={22} />
      上传
      <input accept="video/*" onChange={(event) => event.target.files?.[0] && onFile(event.target.files[0])} type="file" />
    </label>
  );
}

function AssetPreview({ asset }: { asset: AssetResponse | null }) {
  return <RemoteImagePreview title={asset?.filename ?? ""} url={asset?.url ?? ""} />;
}

function RemoteImagePreview({ title, url }: { title: string; url: string }) {
  const objectUrl = useObjectUrl(url);
  return (
    <WorkbenchPreview emptyLabel="暂无素材">
      {objectUrl ? (
        <figure className="asset-preview">
          <img alt={title} src={objectUrl} />
          <figcaption>{title}</figcaption>
        </figure>
      ) : null}
    </WorkbenchPreview>
  );
}

function JobResult({ job }: { job: JobResponse | null }) {
  const outputAssets = useMemo(() => readOutputAssets(job), [job]);
  if (!job) {
    return null;
  }
  return (
    <div className="job-result">
      <span>{job.status}</span>
      {job.error_message ? <p className="error-text">{job.error_message}</p> : null}
      {outputAssets.map((asset) => (
        <button className="secondary-button" key={asset.id} onClick={() => downloadAsset(asset)} type="button">
          <Download size={18} />
          下载
        </button>
      ))}
    </div>
  );
}

function AssetSaveResult({ asset }: { asset: AssetResponse | null }) {
  if (!asset) {
    return null;
  }
  return (
    <div className="job-result">
      <span>{asset.filename}</span>
      <button className="secondary-button" onClick={() => downloadAsset({ id: asset.id, url: asset.url })} type="button">
        <Download size={18} />
        下载
      </button>
    </div>
  );
}

function StatusLine({ error, job }: { error: string; job: JobResponse | null }) {
  if (error) {
    return <p className="error-text">{error}</p>;
  }
  if (!job) {
    return null;
  }
  return <span className="status-text">{job.status}</span>;
}

function useObjectUrl(url: string) {
  const [objectUrl, setObjectUrl] = useState("");
  useEffect(() => {
    if (!url) {
      setObjectUrl("");
      return undefined;
    }
    let alive = true;
    let nextUrl = "";
    gameKnifeApiClient
      .requestBlob(url)
      .then((blob) => {
        if (!alive) {
          return;
        }
        nextUrl = URL.createObjectURL(blob);
        setObjectUrl(nextUrl);
      })
      .catch(() => setObjectUrl(""));
    return () => {
      alive = false;
      if (nextUrl) {
        URL.revokeObjectURL(nextUrl);
      }
    };
  }, [url]);
  return objectUrl;
}

async function waitForJob(jobId: string, maxTries = 10, intervalMs = 350): Promise<JobResponse> {
  let current = await gameKnifeApiClient.getJob(jobId);
  for (let index = 0; index < maxTries && (current.status === "pending" || current.status === "running"); index += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, intervalMs));
    current = await gameKnifeApiClient.getJob(jobId);
  }
  return current;
}

function readOutputAssets(job: JobResponse | null): OutputAssetRef[] {
  const value = job?.result.output_assets;
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is OutputAssetRef => Boolean(item && typeof item === "object" && "id" in item && "url" in item));
}

function requireManualEditCanvas(canvas: HTMLCanvasElement | null) {
  if (!canvas) {
    throw new Error("手动编辑画布尚未准备好。");
  }
  return canvas;
}

function manualEditFilename(name: string) {
  const cleanName = name.trim() || "manual-edit";
  return `${cleanName.replace(/\.[^.]+$/, "")}.png`;
}

async function downloadAsset(asset: OutputAssetRef) {
  const blob = await gameKnifeApiClient.requestBlob(asset.url);
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = `${asset.id}`;
  link.click();
  URL.revokeObjectURL(objectUrl);
}

function formatBbox(value: unknown) {
  return Array.isArray(value) ? value.join(",") : "";
}

function readMessage(value: unknown) {
  return value instanceof Error ? value.message : "操作失败。";
}

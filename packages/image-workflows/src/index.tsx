import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Download, Image as ImageIcon, Play, RefreshCw, Trash2, UploadCloud, Volume2 } from "lucide-react";
import { gameKnifeApiClient } from "@gameknife/api-client";
import type { AssetResponse, JobResponse, OutputAssetRef, SequenceResponse } from "@gameknife/shared-types";
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
  const [error, setError] = useState("");

  useEffect(() => {
    gameKnifeApiClient
      .getSettings()
      .then(setSettings)
      .catch((exc) => setError(readMessage(exc)));
  }, []);

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

async function waitForJob(jobId: string): Promise<JobResponse> {
  let current = await gameKnifeApiClient.getJob(jobId);
  for (let index = 0; index < 10 && (current.status === "pending" || current.status === "running"); index += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 350));
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

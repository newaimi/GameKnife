import { useEffect, useState } from "react";
import { Download, RefreshCw, Save } from "lucide-react";
import { useGameKnifePermissions } from "@gameknife/app-context";
import { gameKnifeApiClient } from "@gameknife/api-client";
import type {
  BiRefNetInstallStatus,
  CharacterRigModelInstallStatus,
  RuntimeSettings,
  StableAudioInstallStatus,
  UpscaleModelInstallStatus,
  VideoGenerationConfig,
} from "@gameknife/shared-types";
import { readMessage } from "../../utils/errors";

const VIDEO_PROVIDER_BASE_URL: Record<VideoGenerationConfig["provider"], string> = {
  aliyun_dashscope: "https://dashscope.aliyuncs.com",
  seedance: "https://ark.cn-beijing.volces.com",
};

function formatAvailable(value: boolean) {
  return value ? "可用" : "不可用";
}

function formatGitSha(value?: string) {
  if (!value || value === "unknown") return "-";
  return value.length > 12 ? value.slice(0, 12) : value;
}

function formatGpuSummary(runtimeInfo: RuntimeSettings["runtime"]) {
  if (!runtimeInfo.cuda_available) {
    return "未检测到 CUDA GPU";
  }

  const currentGpu = runtimeInfo.current_gpu_name ? `，当前：${runtimeInfo.current_gpu_name}` : "";
  return `${runtimeInfo.gpu_count} 张${currentGpu}`;
}

function formatGpuDetail(gpu: RuntimeSettings["runtime"]["gpus"][number]) {
  const memory = gpu.total_memory_mb ? `${gpu.total_memory_mb} MB` : "显存未知";
  const capability = gpu.capability ? `计算能力 ${gpu.capability}` : "计算能力未知";
  return `#${gpu.index} ${gpu.name} / ${memory} / ${capability}`;
}

function formatStableAudioDevice(status: StableAudioInstallStatus | null, baseUrlConfigured?: boolean) {
  if (!baseUrlConfigured) return "未配置";

  const workers = status?.workers ?? [];
  if (!workers.length) return "未知";

  // Stable Audio 服务会返回 cuda:0、cuda:1 这类 worker 细节。
  // 设置页只展示 CPU/CUDA，具体卡号留在服务日志里排查。
  const devices = workers.map((worker) => `${worker.runtime_device ?? worker.device}`.toLowerCase());
  if (devices.some((device) => device.startsWith("cuda"))) return "CUDA";
  if (devices.some((device) => device.startsWith("cpu"))) return "CPU";
  return "未知";
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="key-value">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function buildVideoGenerationPayload(config: VideoGenerationConfig, apiKeyDirty: boolean, apiKey: string) {
  const payload: { provider: VideoGenerationConfig["provider"]; base_url: string; api_key?: string } = {
    provider: config.provider,
    base_url: config.base_url,
  };
  if (apiKeyDirty) {
    payload.api_key = apiKey;
  }
  return payload;
}

export function CommunitySettingsPage() {
  const permissions = useGameKnifePermissions();
  const [settings, setSettings] = useState<RuntimeSettings | null>(null);
  const [installStatus, setInstallStatus] = useState<BiRefNetInstallStatus | null>(null);
  const [rigInstallStatus, setRigInstallStatus] = useState<CharacterRigModelInstallStatus | null>(null);
  const [upscaleInstallStatus, setUpscaleInstallStatus] = useState<UpscaleModelInstallStatus | null>(null);
  const [stableAudioInstallStatus, setStableAudioInstallStatus] = useState<StableAudioInstallStatus | null>(null);
  const [draftVideoConfig, setDraftVideoConfig] = useState<VideoGenerationConfig | null>(null);
  const [videoApiKey, setVideoApiKey] = useState("");
  const [videoApiKeyDirty, setVideoApiKeyDirty] = useState(false);
  const [videoMessage, setVideoMessage] = useState("");
  const [error, setError] = useState("");
  const visibleInstallStatus = installStatus ?? settings?.birefnet.install_status ?? null;
  const visibleRigInstallStatus = rigInstallStatus ?? settings?.character_rig_models.install_status ?? null;
  const visibleUpscaleInstallStatus = upscaleInstallStatus ?? settings?.upscale_models.install_status ?? null;
  const visibleStableAudioInstallStatus = stableAudioInstallStatus ?? settings?.stable_audio.install_status ?? null;
  const isBirefNetInstalling = visibleInstallStatus?.status === "running";
  const isRigInstalling = visibleRigInstallStatus?.status === "running";
  const isUpscaleInstalling = visibleUpscaleInstallStatus?.status === "running";
  const isStableAudioInstalling = visibleStableAudioInstallStatus?.status === "running";
  const isBirefNetInstalled = visibleInstallStatus?.installed ?? visibleInstallStatus?.status === "success";
  const isRigInstalled = visibleRigInstallStatus?.installed ?? visibleRigInstallStatus?.status === "success";
  const isUpscaleInstalled = visibleUpscaleInstallStatus?.installed ?? visibleUpscaleInstallStatus?.status === "success";
  const isStableAudioInstalled = visibleStableAudioInstallStatus?.installed ?? visibleStableAudioInstallStatus?.status === "success";
  const progress = visibleInstallStatus?.progress ?? 0;
  const rigProgress = visibleRigInstallStatus?.progress ?? 0;
  const upscaleProgress = visibleUpscaleInstallStatus?.progress ?? 0;
  const stableAudioProgress = visibleStableAudioInstallStatus?.progress ?? 0;
  const runtimeInfo = settings?.runtime;
  const rigModels = settings?.character_rig_models.models ?? [];
  const readRigModel = (key: "florence" | "grounding_dino" | "sam") => rigModels.find((model) => model.key === key)?.model_id ?? "-";
  const upscaleModels = settings?.upscale_models.models ?? [];
  const readUpscaleModel = (key: "general" | "anime" | "noisy") => upscaleModels.find((model) => model.key === key)?.name ?? "-";
  const stableAudioDevice = formatStableAudioDevice(visibleStableAudioInstallStatus, settings?.stable_audio.base_url_configured);
  const pytorchValue = runtimeInfo
    ? runtimeInfo.pytorch_available
      ? runtimeInfo.pytorch_version ?? "已安装"
      : `不可用${runtimeInfo.error ? `：${runtimeInfo.error}` : ""}`
    : "-";
  const gpuSummary = runtimeInfo ? formatGpuSummary(runtimeInfo) : "-";
  const gpuDetails = runtimeInfo?.gpus.length ? runtimeInfo.gpus.map(formatGpuDetail).join("；") : "-";
  const canManageSettings = permissions.can("settings.manage");

  useEffect(() => {
    const modelMessage = window.sessionStorage.getItem("gameknife-model-settings-message");
    if (modelMessage) {
      window.sessionStorage.removeItem("gameknife-model-settings-message");
    }
    void refreshSettings().then(() => {
      if (modelMessage) {
        setError(modelMessage);
      }
    });
  }, []);

  useEffect(() => {
    const config = settings?.video_generation ?? null;
    setDraftVideoConfig(config);
    setVideoApiKey("");
    setVideoApiKeyDirty(false);
  }, [settings?.video_generation]);

  async function refreshSettings() {
    try {
      setError("");
      const [nextSettings, nextBiRefNetStatus, nextCharacterRigStatus, nextUpscaleStatus, nextStableAudioStatus] = await Promise.all([
        gameKnifeApiClient.getSettings(),
        gameKnifeApiClient.getBiRefNetInstallStatus(),
        gameKnifeApiClient.getCharacterRigModelInstallStatus(),
        gameKnifeApiClient.getUpscaleModelInstallStatus(),
        gameKnifeApiClient.getStableAudioInstallStatus(),
      ]);
      setSettings(nextSettings);
      setInstallStatus(nextBiRefNetStatus);
      setRigInstallStatus(nextCharacterRigStatus);
      setUpscaleInstallStatus(nextUpscaleStatus);
      setStableAudioInstallStatus(nextStableAudioStatus);
    } catch (exc) {
      setError(readMessage(exc));
    }
  }

  async function saveVideoGenerationConfig() {
    if (!draftVideoConfig) return;
    setVideoMessage("正在保存视频 API 配置...");
    try {
      const saved = await gameKnifeApiClient.updateVideoGenerationSettings(buildVideoGenerationPayload(draftVideoConfig, videoApiKeyDirty, videoApiKey));
      setDraftVideoConfig(saved);
      setVideoApiKey("");
      setVideoApiKeyDirty(false);
      await refreshSettings();
      setVideoMessage("视频 API 配置已保存。");
    } catch (exc) {
      setVideoMessage(readMessage(exc));
    }
  }

  async function testVideoGenerationConfig() {
    if (!draftVideoConfig) return;
    setVideoMessage("正在检查视频 API 配置...");
    try {
      const result = await gameKnifeApiClient.testVideoGenerationSettings(buildVideoGenerationPayload(draftVideoConfig, videoApiKeyDirty, videoApiKey));
      setVideoMessage(typeof result.message === "string" ? result.message : "视频 API 配置可用。");
    } catch (exc) {
      setVideoMessage(readMessage(exc));
    }
  }

  async function startBiRefNetInstall() {
    try {
      setError("");
      setInstallStatus(await gameKnifeApiClient.startBiRefNetInstall());
    } catch (exc) {
      setError(readMessage(exc));
    }
  }

  async function startCharacterRigInstall() {
    try {
      setError("");
      setRigInstallStatus(await gameKnifeApiClient.startCharacterRigModelInstall());
    } catch (exc) {
      setError(readMessage(exc));
    }
  }

  async function startUpscaleInstall() {
    try {
      setError("");
      setUpscaleInstallStatus(await gameKnifeApiClient.startUpscaleModelInstall());
    } catch (exc) {
      setError(readMessage(exc));
    }
  }

  async function startStableAudioInstall() {
    try {
      setError("");
      setStableAudioInstallStatus(await gameKnifeApiClient.startStableAudioInstall());
    } catch (exc) {
      setError(readMessage(exc));
    }
  }

  return (
    <section className="settings-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">本地部署设置</p>
          <h1>系统设置</h1>
          <p>这里展示后端当前实际运行配置。涉及模型尺寸、上传上限、存储目录的配置通过环境变量修改后重启服务。</p>
        </div>
        <button className="ghost" onClick={() => void refreshSettings()} type="button">
          <RefreshCw size={18} />
          刷新状态
        </button>
      </div>

      {error ? <p className="error-text">{error}</p> : null}

      <div className="settings-grid">
        <section className="config-card wide">
          <div className="config-card-title">
            <h2>系统</h2>
            <span>FastAPI</span>
          </div>
          <KeyValue label="版本" value={settings?.system.app_version ?? "-"} />
          <KeyValue label="构建号" value={settings?.system.build_number ?? "-"} />
          <KeyValue label="提交" value={formatGitSha(settings?.system.git_sha)} />
          <KeyValue label="构建时间" value={settings?.system.build_time ?? "-"} />
          <KeyValue label="上传上限" value={`${settings?.system.max_upload_mb ?? "-"} MB`} />
          <KeyValue label="存储目录" value={settings?.system.storage_root ?? "-"} />
          <KeyValue label="数据库" value={settings?.system.database_path ?? "-"} />
          <KeyValue label="允许来源" value={settings?.system.cors_origins.join("，") || "-"} />
          <KeyValue label="Python" value={runtimeInfo?.python_version ?? "-"} />
          <KeyValue label="运行平台" value={runtimeInfo?.platform ?? "-"} />
          <KeyValue label="PyTorch" value={pytorchValue} />
          <KeyValue label="CUDA" value={runtimeInfo ? formatAvailable(runtimeInfo.cuda_available) : "-"} />
          <KeyValue label="CUDA 版本" value={runtimeInfo?.cuda_version ?? "-"} />
          <KeyValue label="cuDNN" value={runtimeInfo?.cudnn_version ?? "-"} />
          <KeyValue label="MPS" value={runtimeInfo ? formatAvailable(runtimeInfo.mps_available) : "-"} />
          <KeyValue label="GPU" value={gpuSummary} />
          <KeyValue label="GPU 明细" value={gpuDetails} />
        </section>

        {draftVideoConfig ? (
          <section className="config-card wide">
            <div className="config-card-title">
              <h2>视频生成 API</h2>
              <span>{draftVideoConfig.api_key_configured ? "已配置密钥" : "未配置密钥"}</span>
            </div>
            <label className="number-field">
              <span>供应商</span>
              <select
                value={draftVideoConfig.provider}
                disabled={!canManageSettings}
                onChange={(event) => {
                  const provider = event.target.value as VideoGenerationConfig["provider"];
                  setDraftVideoConfig((current) => (current ? { ...current, provider, base_url: VIDEO_PROVIDER_BASE_URL[provider] } : current));
                }}
              >
                <option value="aliyun_dashscope">阿里云百炼 / HappyHorse</option>
                <option value="seedance">火山引擎 / Seedance</option>
              </select>
            </label>
            <label className="number-field">
              <span>Base URL</span>
              <input disabled={!canManageSettings} value={draftVideoConfig.base_url} onChange={(event) => setDraftVideoConfig((current) => (current ? { ...current, base_url: event.target.value } : current))} />
            </label>
            <label className="number-field">
              <span>API Key</span>
              <input
                type="password"
                value={videoApiKey}
                disabled={!canManageSettings}
                placeholder={draftVideoConfig.masked_api_key ?? "未配置"}
                onChange={(event) => {
                  setVideoApiKey(event.target.value);
                  setVideoApiKeyDirty(true);
                }}
              />
            </label>
            <div className="settings-inline-actions">
              <button
                className="ghost compact"
                type="button"
                disabled={!canManageSettings}
                onClick={() => {
                  setVideoApiKey("");
                  setVideoApiKeyDirty(true);
                }}
              >
                清空密钥
              </button>
              <span>不填写会保留当前密钥。</span>
            </div>
            <div className="settings-actions">
              <button className="primary" type="button" disabled={!canManageSettings} onClick={() => void saveVideoGenerationConfig()}>
                <Save size={18} />
                保存视频 API
              </button>
              <button className="ghost" type="button" disabled={!canManageSettings} onClick={() => void testVideoGenerationConfig()}>
                <RefreshCw size={18} />
                检查配置
              </button>
            </div>
            {videoMessage ? <p className="settings-message">{videoMessage}</p> : null}
          </section>
        ) : null}

        <section className="config-card">
          <div className="config-card-title">
            <h2>BiRefNet</h2>
            <span>{settings?.birefnet.device ?? "未知"}</span>
          </div>
          <KeyValue label="模型" value={settings?.birefnet.model_id ?? "-"} />
          <KeyValue label="输入尺寸" value={`${settings?.birefnet.model_input_size ?? "-"} px`} />
          <KeyValue label="GPU 并发" value={`${settings?.birefnet.gpu_concurrency ?? 1}`} />
          <KeyValue label="加载方式" value={settings?.birefnet.lazy_load ? "设置页手动安装后使用" : "启动时加载"} />
          <div className="install-block">
            {!isBirefNetInstalled ? (
              <button className="primary install-button" disabled={isBirefNetInstalling || !canManageSettings} onClick={startBiRefNetInstall} type="button">
                <Download size={18} />
                下载安装模型文件
              </button>
            ) : null}
            <div className="progress-track" aria-label="BiRefNet 安装进度">
              <div className="progress-bar" style={{ width: `${progress}%` }} />
            </div>
            <div className={`install-message ${visibleInstallStatus?.status === "failed" ? "failed" : ""}`}>
              <span>{visibleInstallStatus?.message ?? "尚未手动安装。"}</span>
              <strong>{progress}%</strong>
            </div>
            {visibleInstallStatus?.error ? <p className="install-error">{visibleInstallStatus.error}</p> : null}
          </div>
        </section>

        <section className="config-card">
          <div className="config-card-title">
            <h2>骨骼拆分模型</h2>
            <span>{settings?.character_rig_models.device ?? "未知"}</span>
          </div>
          <KeyValue label="素材描述" value={readRigModel("florence")} />
          <KeyValue label="候选检测" value={readRigModel("grounding_dino")} />
          <KeyValue label="Mask 精修" value={readRigModel("sam")} />
          <KeyValue label="加载方式" value={settings?.character_rig_models.lazy_load ? "手动安装后使用" : "启动时加载"} />
          <div className="install-block">
            {!isRigInstalled ? (
              <button className="primary install-button" disabled={isRigInstalling || !canManageSettings} onClick={startCharacterRigInstall} type="button">
                <Download size={18} />
                下载安装模型文件
              </button>
            ) : null}
            <div className="progress-track" aria-label="骨骼拆分模型安装进度">
              <div className="progress-bar" style={{ width: `${rigProgress}%` }} />
            </div>
            <div className={`install-message ${visibleRigInstallStatus?.status === "failed" ? "failed" : ""}`}>
              <span>{visibleRigInstallStatus?.message ?? "尚未手动安装。"}</span>
              <strong>{rigProgress}%</strong>
            </div>
            {visibleRigInstallStatus?.error ? <p className="install-error">{visibleRigInstallStatus.error}</p> : null}
          </div>
        </section>

        <section className="config-card">
          <div className="config-card-title">
            <h2>图片放大模型</h2>
            <span>{settings?.upscale_models.device ?? "未知"}</span>
          </div>
          <KeyValue label="通用素材" value={readUpscaleModel("general")} />
          <KeyValue label="动漫插画" value={readUpscaleModel("anime")} />
          <KeyValue label="噪点压缩" value={readUpscaleModel("noisy")} />
          <KeyValue label="加载方式" value={settings?.upscale_models.lazy_load ? "手动安装后使用" : "启动时加载"} />
          <div className="install-block">
            {!isUpscaleInstalled ? (
              <button className="primary install-button" disabled={isUpscaleInstalling || !canManageSettings} onClick={startUpscaleInstall} type="button">
                <Download size={18} />
                下载安装模型文件
              </button>
            ) : null}
            <div className="progress-track" aria-label="图片放大模型安装进度">
              <div className="progress-bar" style={{ width: `${upscaleProgress}%` }} />
            </div>
            <div className={`install-message ${visibleUpscaleInstallStatus?.status === "failed" ? "failed" : ""}`}>
              <span>{visibleUpscaleInstallStatus?.message ?? "尚未手动安装。"}</span>
              <strong>{upscaleProgress}%</strong>
            </div>
            {visibleUpscaleInstallStatus?.error ? <p className="install-error">{visibleUpscaleInstallStatus.error}</p> : null}
          </div>
        </section>

        <section className="config-card">
          <div className="config-card-title">
            <h2>Stable Audio</h2>
            <span>{stableAudioDevice}</span>
          </div>
          <KeyValue label="模型" value={settings?.stable_audio.model_id ?? "-"} />
          <KeyValue label="服务" value={settings?.stable_audio.device ?? "-"} />
          <KeyValue label="Worker" value={stableAudioDevice} />
          <KeyValue label="队列" value={`${visibleStableAudioInstallStatus?.queued ?? 0} / ${visibleStableAudioInstallStatus?.queue_size ?? "-"}`} />
          <KeyValue label="加载方式" value={settings?.stable_audio.lazy_load ? "手动安装后使用" : "启动时加载"} />
          <KeyValue label="权重许可" value="Hugging Face 许可确认后安装" />
          <div className="install-block">
            {!isStableAudioInstalled ? (
              <button className="primary install-button" disabled={isStableAudioInstalling || !settings?.stable_audio.base_url_configured || !canManageSettings} onClick={startStableAudioInstall} type="button">
                <Download size={18} />
                下载安装模型文件
              </button>
            ) : null}
            <div className="progress-track" aria-label="Stable Audio 安装进度">
              <div className="progress-bar" style={{ width: `${stableAudioProgress}%` }} />
            </div>
            <div className={`install-message ${visibleStableAudioInstallStatus?.status === "failed" ? "failed" : ""}`}>
              <span>{visibleStableAudioInstallStatus?.message ?? "尚未手动安装。"}</span>
              <strong>{stableAudioProgress}%</strong>
            </div>
            {visibleStableAudioInstallStatus?.error ? <p className="install-error">{visibleStableAudioInstallStatus.error}</p> : null}
          </div>
        </section>
      </div>
    </section>
  );
}

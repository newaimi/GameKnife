import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { RefreshCw, Save } from "lucide-react";
import { useGameKnifePermissions } from "@gameknife/app-context";
import { gameKnifeApiClient } from "@gameknife/api-client";
import type { TFunction } from "@gameknife/i18n";
import { Button, FeedbackMessage } from "@gameknife/ui-kit";
import type {
  BiRefNetInstallStatus,
  RuntimeSettings,
  StableAudioInstallStatus,
  UpscaleModelInstallStatus,
  VideoGenerationConfig,
} from "@gameknife/shared-types";
import { ModelInstallStatusPanel } from "../../components/ModelInstallStatusPanel";
import { readMessage } from "../../utils/errors";

const VIDEO_PROVIDER_BASE_URL: Record<VideoGenerationConfig["provider"], string> = {
  aliyun_dashscope: "https://dashscope.aliyuncs.com",
  seedance: "https://ark.cn-beijing.volces.com",
};

function formatAvailable(value: boolean, t: TFunction) {
  return value ? t("values.available") : t("values.unavailable");
}

function formatGitSha(value?: string) {
  if (!value || value === "unknown") return "-";
  return value.length > 12 ? value.slice(0, 12) : value;
}

function formatGpuSummary(runtimeInfo: RuntimeSettings["runtime"], t: TFunction) {
  if (!runtimeInfo.cuda_available) {
    return t("values.noCudaGpu");
  }
  return runtimeInfo.current_gpu_name
    ? t("values.gpuSummary", { count: runtimeInfo.gpu_count, current: runtimeInfo.current_gpu_name })
    : t("values.gpuCount", { count: runtimeInfo.gpu_count });
}

function formatGpuDetail(gpu: RuntimeSettings["runtime"]["gpus"][number], t: TFunction) {
  const memory = gpu.total_memory_mb ? `${gpu.total_memory_mb} MB` : t("values.unknownMemory");
  const capability = gpu.capability ? t("values.computeCapability", { value: gpu.capability }) : t("values.unknownComputeCapability");
  return `#${gpu.index} ${gpu.name} / ${memory} / ${capability}`;
}

function formatStableAudioDevice(status: StableAudioInstallStatus | null, baseUrlConfigured: boolean | undefined, t: TFunction) {
  if (!baseUrlConfigured) return t("values.notConfigured");

  const workers = status?.workers ?? [];
  if (!workers.length) return t("values.unknown");

  // Stable Audio returns worker details such as cuda:0 and cuda:1.
  // Settings shows only CPU/CUDA; exact device indexes remain available in service logs.
  const devices = workers.map((worker) => `${worker.runtime_device ?? worker.device}`.toLowerCase());
  if (devices.some((device) => device.startsWith("cuda"))) return "CUDA";
  if (devices.some((device) => device.startsWith("cpu"))) return "CPU";
  return t("values.unknown");
}

function formatModelDevice(device: string | undefined, t: TFunction) {
  if (!device || device.toLowerCase() === "unknown") return t("values.unknown");
  return device;
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
  const { t } = useTranslation("settings");
  const permissions = useGameKnifePermissions();
  const [settings, setSettings] = useState<RuntimeSettings | null>(null);
  const [installStatus, setInstallStatus] = useState<BiRefNetInstallStatus | null>(null);
  const [upscaleInstallStatus, setUpscaleInstallStatus] = useState<UpscaleModelInstallStatus | null>(null);
  const [stableAudioInstallStatus, setStableAudioInstallStatus] = useState<StableAudioInstallStatus | null>(null);
  const [draftVideoConfig, setDraftVideoConfig] = useState<VideoGenerationConfig | null>(null);
  const [videoApiKey, setVideoApiKey] = useState("");
  const [videoApiKeyDirty, setVideoApiKeyDirty] = useState(false);
  const [videoMessage, setVideoMessage] = useState("");
  const [error, setError] = useState("");
  const visibleInstallStatus = installStatus ?? settings?.birefnet.install_status ?? null;
  const visibleUpscaleInstallStatus = upscaleInstallStatus ?? settings?.upscale_models.install_status ?? null;
  const visibleStableAudioInstallStatus = stableAudioInstallStatus ?? settings?.stable_audio.install_status ?? null;
  const runtimeInfo = settings?.runtime;
  const upscaleModels = settings?.upscale_models.models ?? [];
  const readUpscaleModel = (key: "general" | "anime" | "noisy") => upscaleModels.find((model) => model.key === key)?.name ?? "-";
  const stableAudioDevice = formatStableAudioDevice(visibleStableAudioInstallStatus, settings?.stable_audio.base_url_configured, t);
  const pytorchValue = runtimeInfo
    ? runtimeInfo.pytorch_available
      ? runtimeInfo.pytorch_version ?? t("values.installed")
      : runtimeInfo.error
        ? t("values.unavailableWithError", { error: runtimeInfo.error })
        : t("values.unavailable")
    : "-";
  const gpuSummary = runtimeInfo ? formatGpuSummary(runtimeInfo, t) : "-";
  const gpuDetails = runtimeInfo?.gpus.length ? runtimeInfo.gpus.map((gpu) => formatGpuDetail(gpu, t)).join("; ") : "-";
  const canManageSettings = permissions.can("settings.manage");

  useEffect(() => {
    const requiredModel = window.sessionStorage.getItem("gameknife-required-model");
    if (requiredModel) {
      window.sessionStorage.removeItem("gameknife-required-model");
    }
    void refreshSettings().then(() => {
      if (requiredModel) {
        setError(t("models.required", { model: t(`models.names.${requiredModel}`) }));
      }
    });
  }, [t]);

  useEffect(() => {
    const config = settings?.video_generation ?? null;
    setDraftVideoConfig(config);
    setVideoApiKey("");
    setVideoApiKeyDirty(false);
  }, [settings?.video_generation]);

  async function refreshSettings() {
    try {
      setError("");
      const [nextSettings, nextBiRefNetStatus, nextUpscaleStatus, nextStableAudioStatus] = await Promise.all([
        gameKnifeApiClient.getSettings(),
        gameKnifeApiClient.getBiRefNetInstallStatus(),
        gameKnifeApiClient.getUpscaleModelInstallStatus(),
        gameKnifeApiClient.getStableAudioInstallStatus(),
      ]);
      setSettings(nextSettings);
      setInstallStatus(nextBiRefNetStatus);
      setUpscaleInstallStatus(nextUpscaleStatus);
      setStableAudioInstallStatus(nextStableAudioStatus);
    } catch (exc) {
      setError(readMessage(exc));
    }
  }

  async function saveVideoGenerationConfig() {
    if (!draftVideoConfig) return;
    setVideoMessage(t("video.saving"));
    try {
      const saved = await gameKnifeApiClient.updateVideoGenerationSettings(buildVideoGenerationPayload(draftVideoConfig, videoApiKeyDirty, videoApiKey));
      setDraftVideoConfig(saved);
      setVideoApiKey("");
      setVideoApiKeyDirty(false);
      await refreshSettings();
      setVideoMessage(t("video.saved"));
    } catch (exc) {
      setVideoMessage(readMessage(exc));
    }
  }

  async function testVideoGenerationConfig() {
    if (!draftVideoConfig) return;
    setVideoMessage(t("video.testing"));
    try {
      await gameKnifeApiClient.testVideoGenerationSettings(buildVideoGenerationPayload(draftVideoConfig, videoApiKeyDirty, videoApiKey));
      setVideoMessage(t("video.available"));
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
          <p className="eyebrow">{t("eyebrow")}</p>
          <h1>{t("title")}</h1>
          <p>{t("description")}</p>
        </div>
        <Button onClick={() => void refreshSettings()}>
          <RefreshCw size={18} />
          {t("refreshStatus")}
        </Button>
      </div>

      {error ? <FeedbackMessage tone="danger">{error}</FeedbackMessage> : null}

      <div className="settings-grid">
        <section className="config-card wide">
          <div className="config-card-title">
            <h2>{t("system")}</h2>
            <span>FastAPI</span>
          </div>
          <KeyValue label={t("labels.version")} value={settings?.system.app_version ?? "-"} />
          <KeyValue label={t("labels.buildNumber")} value={settings?.system.build_number ?? "-"} />
          <KeyValue label={t("labels.commit")} value={formatGitSha(settings?.system.git_sha)} />
          <KeyValue label={t("labels.buildTime")} value={settings?.system.build_time ?? "-"} />
          <KeyValue label={t("labels.uploadLimit")} value={`${settings?.system.max_upload_mb ?? "-"} MB`} />
          <KeyValue label={t("labels.storageDirectory")} value={settings?.system.storage_root ?? "-"} />
          <KeyValue label={t("labels.database")} value={settings?.system.database_path ?? "-"} />
          <KeyValue label={t("labels.allowedOrigins")} value={settings?.system.cors_origins.join(", ") || "-"} />
          <KeyValue label="Python" value={runtimeInfo?.python_version ?? "-"} />
          <KeyValue label={t("labels.platform")} value={runtimeInfo?.platform ?? "-"} />
          <KeyValue label="PyTorch" value={pytorchValue} />
          <KeyValue label="CUDA" value={runtimeInfo ? formatAvailable(runtimeInfo.cuda_available, t) : "-"} />
          <KeyValue label={t("labels.cudaVersion")} value={runtimeInfo?.cuda_version ?? "-"} />
          <KeyValue label="cuDNN" value={runtimeInfo?.cudnn_version ?? "-"} />
          <KeyValue label="MPS" value={runtimeInfo ? formatAvailable(runtimeInfo.mps_available, t) : "-"} />
          <KeyValue label="GPU" value={gpuSummary} />
          <KeyValue label={t("labels.gpuDetails")} value={gpuDetails} />
        </section>

        {draftVideoConfig ? (
          <section className="config-card wide">
            <div className="config-card-title">
              <h2>{t("video.title")}</h2>
              <span>{draftVideoConfig.api_key_configured ? t("video.configuredKey") : t("video.unconfiguredKey")}</span>
            </div>
            <label className="number-field">
              <span>{t("labels.provider")}</span>
              <select
                value={draftVideoConfig.provider}
                disabled={!canManageSettings}
                onChange={(event) => {
                  const provider = event.target.value as VideoGenerationConfig["provider"];
                  setDraftVideoConfig((current) => (current ? { ...current, provider, base_url: VIDEO_PROVIDER_BASE_URL[provider] } : current));
                }}
              >
                <option value="aliyun_dashscope">{t("video.aliyun")}</option>
                <option value="seedance">{t("video.seedance")}</option>
              </select>
            </label>
            <label className="number-field">
              <span>{t("labels.baseUrl")}</span>
              <input disabled={!canManageSettings} value={draftVideoConfig.base_url} onChange={(event) => setDraftVideoConfig((current) => (current ? { ...current, base_url: event.target.value } : current))} />
            </label>
            <label className="number-field">
              <span>{t("labels.apiKey")}</span>
              <input
                type="password"
                value={videoApiKey}
                disabled={!canManageSettings}
                placeholder={draftVideoConfig.masked_api_key ?? t("values.notConfigured")}
                onChange={(event) => {
                  setVideoApiKey(event.target.value);
                  setVideoApiKeyDirty(true);
                }}
              />
            </label>
            <div className="settings-inline-actions">
              <Button
                size="small"
                disabled={!canManageSettings}
                onClick={() => {
                  setVideoApiKey("");
                  setVideoApiKeyDirty(true);
                }}
              >
                {t("video.clearKey")}
              </Button>
              <span>{t("video.keyHint")}</span>
            </div>
            <div className="settings-actions">
              <Button variant="primary" disabled={!canManageSettings} onClick={() => void saveVideoGenerationConfig()}>
                <Save size={18} />
                {t("video.save")}
              </Button>
              <Button disabled={!canManageSettings} onClick={() => void testVideoGenerationConfig()}>
                <RefreshCw size={18} />
                {t("video.test")}
              </Button>
            </div>
            {videoMessage ? <p className="settings-message">{videoMessage}</p> : null}
          </section>
        ) : null}

        <section className="config-card">
          <div className="config-card-title">
            <h2>BiRefNet</h2>
            <span>{formatModelDevice(settings?.birefnet.device, t)}</span>
          </div>
          <KeyValue label={t("labels.model")} value={settings?.birefnet.model_id ?? "-"} />
          <KeyValue label={t("labels.inputSize")} value={`${settings?.birefnet.model_input_size ?? "-"} px`} />
          <KeyValue label={t("labels.gpuConcurrency")} value={`${settings?.birefnet.gpu_concurrency ?? 1}`} />
          <KeyValue label={t("labels.loadingMode")} value={settings?.birefnet.lazy_load ? t("values.manualInstallFromSettings") : t("values.loadAtStartup")} />
          <ModelInstallStatusPanel label="BiRefNet" status={visibleInstallStatus} installDisabled={!canManageSettings} onInstall={startBiRefNetInstall} />
        </section>

        <section className="config-card">
          <div className="config-card-title">
            <h2>{t("models.upscale")}</h2>
            <span>{formatModelDevice(settings?.upscale_models.device, t)}</span>
          </div>
          <KeyValue label={t("labels.generalAssets")} value={readUpscaleModel("general")} />
          <KeyValue label={t("labels.animeIllustration")} value={readUpscaleModel("anime")} />
          <KeyValue label={t("labels.noiseReduction")} value={readUpscaleModel("noisy")} />
          <KeyValue label={t("labels.loadingMode")} value={settings?.upscale_models.lazy_load ? t("values.manualInstall") : t("values.loadAtStartup")} />
          <ModelInstallStatusPanel label={t("models.upscale")} status={visibleUpscaleInstallStatus} installDisabled={!canManageSettings} onInstall={startUpscaleInstall} />
        </section>

        <section className="config-card">
          <div className="config-card-title">
            <h2>Stable Audio</h2>
            <span>{stableAudioDevice}</span>
          </div>
          <KeyValue label={t("labels.model")} value={settings?.stable_audio.model_id ?? "-"} />
          <KeyValue label={t("labels.service")} value={settings?.stable_audio.device ? t("values.standaloneSfxService") : "-"} />
          <KeyValue label={t("labels.worker")} value={stableAudioDevice} />
          <KeyValue label={t("labels.queue")} value={`${visibleStableAudioInstallStatus?.queued ?? 0} / ${visibleStableAudioInstallStatus?.queue_size ?? "-"}`} />
          <KeyValue label={t("labels.loadingMode")} value={settings?.stable_audio.lazy_load ? t("values.manualInstall") : t("values.loadAtStartup")} />
          <KeyValue label={t("labels.weightsLicense")} value={t("values.licenseConfirmation")} />
          <ModelInstallStatusPanel
            label="Stable Audio"
            status={visibleStableAudioInstallStatus}
            installDisabled={!settings?.stable_audio.base_url_configured || !canManageSettings}
            onInstall={startStableAudioInstall}
          />
        </section>
      </div>
    </section>
  );
}

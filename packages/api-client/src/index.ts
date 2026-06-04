import type {
  AppContext,
  AssetResponse,
  BiRefNetInstallStatus,
  CharacterRigModelInstallStatus,
  CharacterRigResponse,
  JobPageResponse,
  JobResponse,
  RuntimeSettings,
  SequenceResponse,
  StableAudioInstallStatus,
  UpscaleModelInstallStatus,
  VideoGenerationConfig,
} from "@gameknife/shared-types";

export interface GameKnifeApiClientOptions {
  baseUrl?: string;
}

type ViteImportMeta = ImportMeta & {
  env?: {
    VITE_API_BASE_URL?: string;
  };
};

export class GameKnifeApiClient {
  private readonly baseUrl: string;

  constructor(options: GameKnifeApiClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? "";
  }

  async getContext(): Promise<AppContext> {
    return this.requestJson<AppContext>("/api/context");
  }

  async getSettings(): Promise<RuntimeSettings> {
    return this.requestJson<RuntimeSettings>("/api/settings");
  }

  async uploadImage(file: File): Promise<AssetResponse> {
    const form = new FormData();
    form.append("file", file);
    return this.requestJson<AssetResponse>("/api/assets/images", {
      method: "POST",
      body: form,
    });
  }

  async uploadVideo(file: File): Promise<AssetResponse> {
    const form = new FormData();
    form.append("file", file);
    return this.requestJson<AssetResponse>("/api/assets/videos", {
      method: "POST",
      body: form,
    });
  }

  async saveManualEditAsset(file: File, name?: string, sourceAssetId?: string, sourceContext?: string): Promise<AssetResponse> {
    const form = new FormData();
    form.append("file", file);
    if (name) {
      form.append("name", name);
    }
    if (sourceAssetId) {
      form.append("source_asset_id", sourceAssetId);
    }
    if (sourceContext) {
      form.append("source_context", sourceContext);
    }
    return this.requestJson<AssetResponse>("/api/manual-edits/save", {
      method: "POST",
      body: form,
    });
  }

  async listJobs(): Promise<JobResponse[]> {
    return this.requestJson<JobResponse[]>("/api/jobs");
  }

  async getJob(jobId: string): Promise<JobResponse> {
    return this.requestJson<JobResponse>(`/api/jobs/${jobId}`);
  }

  async listJobHistory(
    params: { page?: number; pageSize?: number; category?: string; createdFrom?: string; createdTo?: string; downloadable?: boolean } = {},
  ): Promise<JobPageResponse> {
    const search = new URLSearchParams();
    search.set("page", String(params.page ?? 1));
    search.set("page_size", String(params.pageSize ?? 20));
    search.set("category", params.category ?? "all");
    if (params.createdFrom) {
      search.set("created_from", params.createdFrom);
    }
    if (params.createdTo) {
      search.set("created_to", params.createdTo);
    }
    if (params.downloadable) {
      search.set("downloadable", "true");
    }
    return this.requestJson<JobPageResponse>(`/api/jobs/history?${search.toString()}`);
  }

  async deleteJob(jobId: string): Promise<void> {
    await this.requestVoid(`/api/jobs/${jobId}`, { method: "DELETE" });
  }

  async createUpscaleJob(inputAssetId: string, parameters: object): Promise<JobResponse> {
    return this.createAssetJob("/api/jobs/upscale", inputAssetId, parameters);
  }

  async createBackgroundRemoveJob(inputAssetId: string, parameters: object): Promise<JobResponse> {
    return this.createAssetJob("/api/jobs/background-remove", inputAssetId, parameters);
  }

  async createSoundEffectJob(payload: {
    prompt: string;
    duration_seconds: number;
    seed?: number | null;
    steps: number;
    cfg_scale: number;
  }): Promise<JobResponse> {
    return this.requestJson<JobResponse>("/api/jobs/sound-effect", {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify(payload),
    });
  }

  async createAssetBoardRegionJob(inputAssetId: string, parameters: object): Promise<JobResponse> {
    return this.createAssetJob("/api/jobs/asset-board/regions", inputAssetId, parameters);
  }

  async createAssetBoardCutoutJob(inputAssetId: string, parameters: object): Promise<JobResponse> {
    return this.createAssetJob("/api/jobs/asset-board/cutout", inputAssetId, parameters);
  }

  async createAssetBoardRefineJob(cutoutAssetId: string, parameters: object): Promise<JobResponse> {
    return this.requestJson<JobResponse>("/api/jobs/asset-board/refine", {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ cutout_asset_id: cutoutAssetId, parameters }),
    });
  }

  async createAssetBoardExportJob(payload: {
    cutoutAssetId: string;
    selectedComponentIds?: number[];
    components?: object[];
    parameters?: object;
  }): Promise<JobResponse> {
    return this.requestJson<JobResponse>("/api/jobs/asset-board/export", {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({
        cutout_asset_id: payload.cutoutAssetId,
        selected_component_ids: payload.selectedComponentIds ?? [],
        components: payload.components ?? [],
        parameters: payload.parameters ?? {},
      }),
    });
  }

  async uploadSequenceFrames(files: File[], name: string, fps: number): Promise<SequenceResponse> {
    const form = new FormData();
    for (const file of files) {
      form.append("files", file);
    }
    form.append("name", name);
    form.append("fps", String(fps));
    return this.requestJson<SequenceResponse>("/api/sequences/import", {
      method: "POST",
      body: form,
    });
  }

  async listSequences(): Promise<SequenceResponse[]> {
    return this.requestJson<SequenceResponse[]>("/api/sequences");
  }

  async getSequence(sequenceId: string): Promise<SequenceResponse> {
    return this.requestJson<SequenceResponse>(`/api/sequences/${sequenceId}`);
  }

  async updateSequence(sequenceId: string, payload: object): Promise<SequenceResponse> {
    return this.requestJson<SequenceResponse>(`/api/sequences/${sequenceId}`, {
      method: "PATCH",
      headers: jsonHeaders(),
      body: JSON.stringify(payload),
    });
  }

  async updateSequenceFrames(sequenceId: string, frames: object[]): Promise<SequenceResponse> {
    return this.requestJson<SequenceResponse>(`/api/sequences/${sequenceId}/frames`, {
      method: "PATCH",
      headers: jsonHeaders(),
      body: JSON.stringify({ frames }),
    });
  }

  async createSequenceCleanJob(sequenceId: string, parameters: object): Promise<JobResponse> {
    return this.requestJson<JobResponse>(`/api/sequences/${sequenceId}/clean`, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ parameters }),
    });
  }

  async createSequenceFramesExportJob(sequenceId: string, parameters: object): Promise<JobResponse> {
    return this.requestJson<JobResponse>(`/api/sequences/${sequenceId}/export/frames`, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ parameters }),
    });
  }

  async createSequenceSpineExportJob(sequenceId: string, parameters: object): Promise<JobResponse> {
    return this.requestJson<JobResponse>(`/api/sequences/${sequenceId}/export/spine`, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ parameters }),
    });
  }

  async createSequenceFromVideoJob(payload: {
    video_asset_id: string;
    name?: string;
    fps: number;
    max_frames: number;
    start_second?: number;
    duration_seconds?: number | null;
    remove_background?: boolean;
    parameters?: object;
  }): Promise<JobResponse> {
    return this.requestJson<JobResponse>("/api/sequences/from-video", {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({
        video_asset_id: payload.video_asset_id,
        name: payload.name,
        fps: payload.fps,
        max_frames: payload.max_frames,
        start_second: payload.start_second ?? 0,
        duration_seconds: payload.duration_seconds ?? null,
        remove_background: payload.remove_background ?? false,
        parameters: payload.parameters ?? {},
      }),
    });
  }

  async createVideoGenerationJob(payload: {
    input_asset_id: string;
    action: string;
    prompt: string;
    negative_prompt?: string;
    duration: number;
    resolution: string;
    confirmed_external_api: boolean;
  }): Promise<JobResponse> {
    return this.requestJson<JobResponse>("/api/sequences/generate-from-image", {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify(payload),
    });
  }

  async deleteSequence(sequenceId: string): Promise<void> {
    await this.requestVoid(`/api/sequences/${sequenceId}`, { method: "DELETE" });
  }

  async importCharacterRig(file: File, name?: string): Promise<CharacterRigResponse> {
    const form = new FormData();
    form.append("file", file);
    if (name) {
      form.append("name", name);
    }
    return this.requestJson<CharacterRigResponse>("/api/character-rigs/import", {
      method: "POST",
      body: form,
    });
  }

  async listCharacterRigs(): Promise<CharacterRigResponse[]> {
    return this.requestJson<CharacterRigResponse[]>("/api/character-rigs");
  }

  async getCharacterRig(rigId: string): Promise<CharacterRigResponse> {
    return this.requestJson<CharacterRigResponse>(`/api/character-rigs/${rigId}`);
  }

  async updateCharacterRig(rigId: string, payload: { name?: string; export_format?: string }): Promise<CharacterRigResponse> {
    return this.requestJson<CharacterRigResponse>(`/api/character-rigs/${rigId}`, {
      method: "PATCH",
      headers: jsonHeaders(),
      body: JSON.stringify(payload),
    });
  }

  async updateCharacterParts(rigId: string, parts: object[]): Promise<CharacterRigResponse> {
    return this.requestJson<CharacterRigResponse>(`/api/character-rigs/${rigId}/parts`, {
      method: "PATCH",
      headers: jsonHeaders(),
      body: JSON.stringify({ parts }),
    });
  }

  async createCharacterRigAnalyzeJob(rigId: string, parameters: object): Promise<JobResponse> {
    return this.requestJson<JobResponse>(`/api/character-rigs/${rigId}/analyze`, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ parameters }),
    });
  }

  async createCharacterPartRefineJob(rigId: string, partId: string, parameters: object): Promise<JobResponse> {
    return this.requestJson<JobResponse>(`/api/character-rigs/${rigId}/parts/${partId}/refine`, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ parameters }),
    });
  }

  async createCharacterRigSpineExportJob(rigId: string, parameters: object): Promise<JobResponse> {
    return this.requestJson<JobResponse>(`/api/character-rigs/${rigId}/export/spine`, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ parameters }),
    });
  }

  async createCharacterRigDragonBonesExportJob(rigId: string, parameters: object): Promise<JobResponse> {
    return this.requestJson<JobResponse>(`/api/character-rigs/${rigId}/export/dragonbones`, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ parameters }),
    });
  }

  async deleteCharacterRig(rigId: string): Promise<void> {
    await this.requestVoid(`/api/character-rigs/${rigId}`, { method: "DELETE" });
  }

  async getVideoGenerationSettings(): Promise<VideoGenerationConfig> {
    return this.requestJson<VideoGenerationConfig>("/api/settings/video-generation");
  }

  async getBiRefNetInstallStatus(): Promise<BiRefNetInstallStatus> {
    return this.requestJson<BiRefNetInstallStatus>("/api/settings/birefnet/install");
  }

  async startBiRefNetInstall(): Promise<BiRefNetInstallStatus> {
    return this.requestJson<BiRefNetInstallStatus>("/api/settings/birefnet/install", {
      method: "POST",
    });
  }

  async getCharacterRigModelInstallStatus(): Promise<CharacterRigModelInstallStatus> {
    return this.requestJson<CharacterRigModelInstallStatus>("/api/settings/character-rig-models/install");
  }

  async startCharacterRigModelInstall(): Promise<CharacterRigModelInstallStatus> {
    return this.requestJson<CharacterRigModelInstallStatus>("/api/settings/character-rig-models/install", {
      method: "POST",
    });
  }

  async getUpscaleModelInstallStatus(): Promise<UpscaleModelInstallStatus> {
    return this.requestJson<UpscaleModelInstallStatus>("/api/settings/upscale-models/install");
  }

  async startUpscaleModelInstall(): Promise<UpscaleModelInstallStatus> {
    return this.requestJson<UpscaleModelInstallStatus>("/api/settings/upscale-models/install", {
      method: "POST",
    });
  }

  async getStableAudioInstallStatus(): Promise<StableAudioInstallStatus> {
    return this.requestJson<StableAudioInstallStatus>("/api/settings/stable-audio/install");
  }

  async startStableAudioInstall(): Promise<StableAudioInstallStatus> {
    return this.requestJson<StableAudioInstallStatus>("/api/settings/stable-audio/install", {
      method: "POST",
    });
  }

  async updateVideoGenerationSettings(payload: { provider: VideoGenerationConfig["provider"]; base_url: string; api_key?: string }): Promise<VideoGenerationConfig> {
    return this.requestJson<VideoGenerationConfig>("/api/settings/video-generation", {
      method: "PATCH",
      headers: jsonHeaders(),
      body: JSON.stringify(payload),
    });
  }

  async testVideoGenerationSettings(payload: { provider: VideoGenerationConfig["provider"]; base_url: string; api_key?: string }): Promise<Record<string, unknown>> {
    return this.requestJson<Record<string, unknown>>("/api/settings/video-generation/test", {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify(payload),
    });
  }

  async requestBlob(url: string): Promise<Blob> {
    const response = await fetch(this.resolveUrl(url));
    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }
    return response.blob();
  }

  private async requestJson<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(this.resolveUrl(path), init);
    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }
    return response.json() as Promise<T>;
  }

  private async requestVoid(path: string, init?: RequestInit): Promise<void> {
    const response = await fetch(this.resolveUrl(path), init);
    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }
  }

  private async createAssetJob(path: string, inputAssetId: string, parameters: object): Promise<JobResponse> {
    return this.requestJson<JobResponse>(path, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ input_asset_id: inputAssetId, parameters }),
    });
  }

  private resolveUrl(path: string): string {
    if (/^https?:\/\//.test(path)) {
      return path;
    }
    return `${this.baseUrl}${path}`;
  }
}

function readDefaultBaseUrl(): string {
  // 默认同源访问可以满足 Community 本地部署；读取 Vite 配置是为了保留原工程连接外部后端的开发方式。
  // 这里只读取公开的 base url，不读取 token，避免把登录态重新带回开源 Community。
  return ((import.meta as ViteImportMeta).env?.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
}

function jsonHeaders(): HeadersInit {
  return { "Content-Type": "application/json" };
}

async function readErrorMessage(response: Response): Promise<string> {
  const fallback = `请求失败，状态码 ${response.status}`;
  try {
    const data = (await response.json()) as { detail?: string };
    return data.detail || fallback;
  } catch {
    return fallback;
  }
}

export const gameKnifeApiClient = new GameKnifeApiClient({ baseUrl: readDefaultBaseUrl() });

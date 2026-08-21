import type {
  AppContext,
  AssetResponse,
  AssetDetailResponse,
  AssetPageResponse,
  BiRefNetInstallStatus,
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

export interface TaskSubmissionOptions {
  idempotencyKey?: string;
  quoteId?: string;
}

export class ApiClientError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = code;
  }
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

  async listAssets(
    params: { page?: number; pageSize?: number; category?: "all" | "image" | "video" | "audio" | "export"; search?: string } = {},
  ): Promise<AssetPageResponse> {
    const search = new URLSearchParams({
      page: String(params.page ?? 1),
      page_size: String(params.pageSize ?? 24),
      category: params.category ?? "all",
    });
    if (params.search?.trim()) {
      search.set("search", params.search.trim());
    }
    return this.requestJson<AssetPageResponse>(`/api/assets?${search.toString()}`);
  }

  async getAssetMetadata(assetId: string): Promise<AssetDetailResponse> {
    return this.requestJson<AssetDetailResponse>(`/api/assets/${assetId}/metadata`);
  }

  async deleteAsset(assetId: string): Promise<void> {
    await this.requestVoid(`/api/assets/${assetId}`, { method: "DELETE" });
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
    params: {
      page?: number;
      pageSize?: number;
      category?: string;
      createdFrom?: string;
      createdTo?: string;
      downloadable?: boolean;
      deliveryOnly?: boolean;
      status?: "pending" | "running" | "success" | "failed";
    } = {},
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
    if (params.deliveryOnly) {
      search.set("delivery_only", "true");
    }
    if (params.status) {
      search.set("status", params.status);
    }
    return this.requestJson<JobPageResponse>(`/api/jobs/history?${search.toString()}`);
  }

  async deleteJob(jobId: string): Promise<void> {
    await this.requestVoid(`/api/jobs/${jobId}`, { method: "DELETE" });
  }

  async createUpscaleJob(inputAssetId: string, parameters: object, submission?: TaskSubmissionOptions): Promise<JobResponse> {
    return this.createAssetJob("/api/jobs/upscale", inputAssetId, parameters, submission);
  }

  async createBackgroundRemoveJob(inputAssetId: string, parameters: object, submission?: TaskSubmissionOptions): Promise<JobResponse> {
    return this.createAssetJob("/api/jobs/background-remove", inputAssetId, parameters, submission);
  }

  async createSoundEffectJob(payload: {
    prompt: string;
    duration_seconds: number;
    seed?: number | null;
    steps: number;
    cfg_scale: number;
  }, submission?: TaskSubmissionOptions): Promise<JobResponse> {
    return this.requestJson<JobResponse>("/api/jobs/sound-effect", {
      method: "POST",
      headers: jobJsonHeaders(submission),
      body: JSON.stringify(payload),
    });
  }

  async createProjectExportJob(
    payload: { asset_ids: string[]; preset: "generic" | "unity" | "godot"; package_name: string },
    submission?: TaskSubmissionOptions,
  ): Promise<JobResponse> {
    return this.requestJson<JobResponse>("/api/jobs/project-export", {
      method: "POST",
      headers: jobJsonHeaders(submission),
      body: JSON.stringify(payload),
    });
  }

  async createAssetBoardRegionJob(inputAssetId: string, parameters: object, submission?: TaskSubmissionOptions): Promise<JobResponse> {
    return this.createAssetJob("/api/jobs/asset-board/regions", inputAssetId, parameters, submission);
  }

  async createAssetBoardCutoutJob(inputAssetId: string, parameters: object, submission?: TaskSubmissionOptions): Promise<JobResponse> {
    return this.createAssetJob("/api/jobs/asset-board/cutout", inputAssetId, parameters, submission);
  }

  async createAssetBoardRefineJob(cutoutAssetId: string, parameters: object, submission?: TaskSubmissionOptions): Promise<JobResponse> {
    return this.requestJson<JobResponse>("/api/jobs/asset-board/refine", {
      method: "POST",
      headers: jobJsonHeaders(submission),
      body: JSON.stringify({ cutout_asset_id: cutoutAssetId, parameters }),
    });
  }

  async createAssetBoardExportJob(payload: {
    cutoutAssetId: string;
    selectedComponentIds?: number[];
    components?: object[];
    parameters?: object;
  }, submission?: TaskSubmissionOptions): Promise<JobResponse> {
    return this.requestJson<JobResponse>("/api/jobs/asset-board/export", {
      method: "POST",
      headers: jobJsonHeaders(submission),
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

  async createSequenceCleanJob(sequenceId: string, parameters: object, submission?: TaskSubmissionOptions): Promise<JobResponse> {
    return this.requestJson<JobResponse>(`/api/sequences/${sequenceId}/clean`, {
      method: "POST",
      headers: jobJsonHeaders(submission),
      body: JSON.stringify({ parameters }),
    });
  }

  async createSequenceFramesExportJob(sequenceId: string, parameters: object, submission?: TaskSubmissionOptions): Promise<JobResponse> {
    return this.requestJson<JobResponse>(`/api/sequences/${sequenceId}/export/frames`, {
      method: "POST",
      headers: jobJsonHeaders(submission),
      body: JSON.stringify({ parameters }),
    });
  }

  async createSequenceSpineExportJob(sequenceId: string, parameters: object, submission?: TaskSubmissionOptions): Promise<JobResponse> {
    return this.requestJson<JobResponse>(`/api/sequences/${sequenceId}/export/spine`, {
      method: "POST",
      headers: jobJsonHeaders(submission),
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
  }, submission?: TaskSubmissionOptions): Promise<JobResponse> {
    return this.requestJson<JobResponse>("/api/sequences/from-video", {
      method: "POST",
      headers: jobJsonHeaders(submission),
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
  }, submission?: TaskSubmissionOptions): Promise<JobResponse> {
    return this.requestJson<JobResponse>("/api/sequences/generate-from-image", {
      method: "POST",
      headers: jobJsonHeaders(submission),
      body: JSON.stringify(payload),
    });
  }

  async deleteSequence(sequenceId: string): Promise<void> {
    await this.requestVoid(`/api/sequences/${sequenceId}`, { method: "DELETE" });
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
      throw await readApiClientError(response);
    }
    return response.blob();
  }

  private async requestJson<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(this.resolveUrl(path), init);
    if (!response.ok) {
      throw await readApiClientError(response);
    }
    return response.json() as Promise<T>;
  }

  private async requestVoid(path: string, init?: RequestInit): Promise<void> {
    const response = await fetch(this.resolveUrl(path), init);
    if (!response.ok) {
      throw await readApiClientError(response);
    }
  }

  private async createAssetJob(path: string, inputAssetId: string, parameters: object, submission?: TaskSubmissionOptions): Promise<JobResponse> {
    return this.requestJson<JobResponse>(path, {
      method: "POST",
      headers: jobJsonHeaders(submission),
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
  // Same-origin access supports local Community deployment, while the Vite setting preserves external-backend development.
  // Read only the public base URL and never a token, keeping login state out of the open source Community client.
  return ((import.meta as ViteImportMeta).env?.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
}

function jsonHeaders(): HeadersInit {
  return { "Content-Type": "application/json" };
}

function jobJsonHeaders(submission?: TaskSubmissionOptions): HeadersInit {
  const headers = new Headers(jsonHeaders());
  if (submission?.idempotencyKey) {
    headers.set("Idempotency-Key", submission.idempotencyKey);
  }
  if (submission?.quoteId) {
    headers.set("X-GameKnife-Quote-Id", submission.quoteId);
  }
  return headers;
}

async function readApiClientError(response: Response): Promise<ApiClientError> {
  const fallback = `请求失败，状态码 ${response.status}`;
  try {
    const data = (await response.json()) as { detail?: string | { code?: unknown; message?: unknown } };
    if (typeof data.detail === "string") {
      return new ApiClientError(data.detail, response.status);
    }
    if (data.detail && typeof data.detail === "object") {
      const code = typeof data.detail.code === "string" ? data.detail.code : undefined;
      const message = typeof data.detail.message === "string" ? data.detail.message : fallback;
      return new ApiClientError(message, response.status, code);
    }
    return new ApiClientError(fallback, response.status);
  } catch {
    return new ApiClientError(fallback, response.status);
  }
}

export const gameKnifeApiClient = new GameKnifeApiClient({ baseUrl: readDefaultBaseUrl() });

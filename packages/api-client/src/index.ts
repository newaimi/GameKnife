import type { AppContext, AssetResponse, JobPageResponse, JobResponse, SequenceResponse } from "@gameknife/shared-types";

export interface GameKnifeApiClientOptions {
  baseUrl?: string;
}

export class GameKnifeApiClient {
  private readonly baseUrl: string;

  constructor(options: GameKnifeApiClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? "";
  }

  async getContext(): Promise<AppContext> {
    return this.requestJson<AppContext>("/api/context");
  }

  async getSettings(): Promise<Record<string, unknown>> {
    return this.requestJson<Record<string, unknown>>("/api/settings");
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

  async listJobs(): Promise<JobResponse[]> {
    return this.requestJson<JobResponse[]>("/api/jobs");
  }

  async getJob(jobId: string): Promise<JobResponse> {
    return this.requestJson<JobResponse>(`/api/jobs/${jobId}`);
  }

  async listJobHistory(params: { page?: number; pageSize?: number; category?: string; downloadable?: boolean } = {}): Promise<JobPageResponse> {
    const search = new URLSearchParams();
    search.set("page", String(params.page ?? 1));
    search.set("page_size", String(params.pageSize ?? 20));
    search.set("category", params.category ?? "all");
    if (params.downloadable) {
      search.set("downloadable", "true");
    }
    return this.requestJson<JobPageResponse>(`/api/jobs/history?${search.toString()}`);
  }

  async deleteJob(jobId: string): Promise<void> {
    await this.requestVoid(`/api/jobs/${jobId}`, { method: "DELETE" });
  }

  async createUpscaleJob(inputAssetId: string, parameters: Record<string, unknown>): Promise<JobResponse> {
    return this.createAssetJob("/api/jobs/upscale", inputAssetId, parameters);
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

  async createAssetBoardRegionJob(inputAssetId: string, parameters: Record<string, unknown>): Promise<JobResponse> {
    return this.createAssetJob("/api/jobs/asset-board/regions", inputAssetId, parameters);
  }

  async createAssetBoardRefineJob(cutoutAssetId: string, parameters: Record<string, unknown>): Promise<JobResponse> {
    return this.requestJson<JobResponse>("/api/jobs/asset-board/refine", {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ cutout_asset_id: cutoutAssetId, parameters }),
    });
  }

  async createAssetBoardExportJob(payload: {
    cutoutAssetId: string;
    selectedComponentIds?: number[];
    components?: Record<string, unknown>[];
    parameters?: Record<string, unknown>;
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

  async createSequenceCleanJob(sequenceId: string, parameters: Record<string, unknown>): Promise<JobResponse> {
    return this.requestJson<JobResponse>(`/api/sequences/${sequenceId}/clean`, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ parameters }),
    });
  }

  async createSequenceFramesExportJob(sequenceId: string, parameters: Record<string, unknown>): Promise<JobResponse> {
    return this.requestJson<JobResponse>(`/api/sequences/${sequenceId}/export/frames`, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ parameters }),
    });
  }

  async createSequenceSpineExportJob(sequenceId: string, parameters: Record<string, unknown>): Promise<JobResponse> {
    return this.requestJson<JobResponse>(`/api/sequences/${sequenceId}/export/spine`, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ parameters }),
    });
  }

  async deleteSequence(sequenceId: string): Promise<void> {
    await this.requestVoid(`/api/sequences/${sequenceId}`, { method: "DELETE" });
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

  private async createAssetJob(path: string, inputAssetId: string, parameters: Record<string, unknown>): Promise<JobResponse> {
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

export const gameKnifeApiClient = new GameKnifeApiClient();

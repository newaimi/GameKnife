import type { AppContext, AssetResponse } from "@gameknife/shared-types";

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

  private resolveUrl(path: string): string {
    if (/^https?:\/\//.test(path)) {
      return path;
    }
    return `${this.baseUrl}${path}`;
  }
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

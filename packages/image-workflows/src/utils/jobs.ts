import { gameKnifeApiClient } from "@gameknife/api-client";
import type { JobResponse, OutputAssetRef } from "@gameknife/shared-types";

export type JobPollingOptions = {
  maxTries?: number;
  intervalMs?: number;
};

export const JOB_POLLING_PRESETS = {
  standard: { maxTries: 180, intervalMs: 1000 },
  long: { maxTries: 1800, intervalMs: 1000 },
} as const satisfies Record<string, Required<JobPollingOptions>>;

export async function waitForJob(jobId: string, options: JobPollingOptions = JOB_POLLING_PRESETS.standard): Promise<JobResponse> {
  const maxTries = Math.max(1, Math.floor(options.maxTries ?? JOB_POLLING_PRESETS.standard.maxTries));
  const intervalMs = Math.max(300, Math.floor(options.intervalMs ?? JOB_POLLING_PRESETS.standard.intervalMs));

  // 模型推理、外部 API 和独立声效服务的耗时会受队列、模型冷启动和设备状态影响。
  // 默认轮询不能停在几秒内，否则后端已经写入 output_assets 后，前端仍会停留在运行中状态。
  for (let index = 0; index < maxTries; index += 1) {
    const job = await gameKnifeApiClient.getJob(jobId);
    if (job.status === "success" || job.status === "failed") {
      return job;
    }
    await new Promise((resolve) => window.setTimeout(resolve, intervalMs));
  }
  return gameKnifeApiClient.getJob(jobId);
}

export function readJobOutputAssets(job: JobResponse | null | undefined): OutputAssetRef[] {
  const value = job?.result?.output_assets;
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is OutputAssetRef => Boolean(item && typeof item === "object" && "id" in item && "url" in item));
}

export function readFirstJobOutputAsset(job: JobResponse | null | undefined): OutputAssetRef | undefined {
  return readJobOutputAssets(job)[0];
}

export function readTupleNumber(value: unknown): [number, number] | undefined {
  if (!Array.isArray(value) || value.length < 2) {
    return undefined;
  }
  return [Number(value[0]), Number(value[1])];
}

export function readString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

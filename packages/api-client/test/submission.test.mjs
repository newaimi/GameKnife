import assert from "node:assert/strict";
import test from "node:test";
import { ApiClientError, GameKnifeApiClient } from "../dist/index.js";

const submission = { idempotencyKey: "request-1", quoteId: "quote-1" };

const jobCases = [
  ["background_remove", "/api/jobs/background-remove", (client, options) => client.createBackgroundRemoveJob("asset-1", { alpha_smoothing: 0 }, options)],
  ["image_upscale", "/api/jobs/upscale", (client, options) => client.createUpscaleJob("asset-1", { scale: 4 }, options)],
  ["sound_effect_generate", "/api/jobs/sound-effect", (client, options) => client.createSoundEffectJob({ prompt: "step", duration_seconds: 4, steps: 100, cfg_scale: 7 }, options)],
  ["asset_board_region_detect", "/api/jobs/asset-board/regions", (client, options) => client.createAssetBoardRegionJob("asset-1", { alpha_threshold: 16 }, options)],
  ["asset_board_cutout", "/api/jobs/asset-board/cutout", (client, options) => client.createAssetBoardCutoutJob("asset-1", { alpha_threshold: 16 }, options)],
  ["asset_board_region_refine", "/api/jobs/asset-board/refine", (client, options) => client.createAssetBoardRefineJob("cutout-1", { alpha_threshold: 16 }, options)],
  ["asset_board_export", "/api/jobs/asset-board/export", (client, options) => client.createAssetBoardExportJob({ cutoutAssetId: "cutout-1", selectedComponentIds: [1], components: [], parameters: {} }, options)],
  ["sequence_clean", "/api/sequences/sequence-1/clean", (client, options) => client.createSequenceCleanJob("sequence-1", { alpha_threshold: 24 }, options)],
  ["sequence_export_frames", "/api/sequences/sequence-1/export/frames", (client, options) => client.createSequenceFramesExportJob("sequence-1", {}, options)],
  ["sequence_export_spine", "/api/sequences/sequence-1/export/spine", (client, options) => client.createSequenceSpineExportJob("sequence-1", {}, options)],
  ["sequence_video_to_frames", "/api/sequences/from-video", (client, options) => client.createSequenceFromVideoJob({ video_asset_id: "video-1", fps: 12, max_frames: 24 }, options)],
  ["sequence_generate_video", "/api/sequences/generate-from-image", (client, options) => client.createVideoGenerationJob({ input_asset_id: "asset-1", action: "walk", prompt: "", duration: 5, resolution: "720P", confirmed_external_api: true }, options)],
  ["project_export_package", "/api/jobs/project-export", (client, options) => client.createProjectExportJob({ asset_ids: ["asset-1"], preset: "unity", package_name: "characters" }, options)],
];

test("all thirteen job creation methods attach commercial submission headers only when provided", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    return jsonResponse(jobResponse());
  };
  try {
    const client = new GameKnifeApiClient({ baseUrl: "https://studio.test" });
    for (const [, expectedPath, invoke] of jobCases) {
      await invoke(client, submission);
      const withSubmission = calls.at(-1);
      assert.equal(withSubmission.url, `https://studio.test${expectedPath}`);
      const headers = new Headers(withSubmission.init.headers);
      assert.equal(headers.get("Idempotency-Key"), submission.idempotencyKey);
      assert.equal(headers.get("X-GameKnife-Quote-Id"), submission.quoteId);

      await invoke(client, undefined);
      const withoutSubmission = calls.at(-1);
      const directHeaders = new Headers(withoutSubmission.init.headers);
      assert.equal(directHeaders.get("Idempotency-Key"), null);
      assert.equal(directHeaders.get("X-GameKnife-Quote-Id"), null);
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("the submission test matrix covers each public job type exactly once", () => {
  const expected = new Set([
    "background_remove",
    "asset_board_region_detect",
    "asset_board_cutout",
    "asset_board_region_refine",
    "asset_board_export",
    "image_upscale",
    "sequence_clean",
    "sequence_generate_video",
    "sequence_video_to_frames",
    "sequence_export_frames",
    "sequence_export_spine",
    "sound_effect_generate",
    "project_export_package",
  ]);
  assert.deepEqual(new Set(jobCases.map(([jobType]) => jobType)), expected);
  assert.equal(jobCases.length, expected.size);
});

test("ordinary uploads and CRUD requests never receive task submission headers", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    return jsonResponse(String(url).endsWith("/api/assets/images") ? assetResponse() : sequenceResponse());
  };
  try {
    const client = new GameKnifeApiClient({ baseUrl: "https://studio.test" });
    await client.uploadImage(new File(["image"], "sprite.png", { type: "image/png" }));
    await client.listAssets({ category: "image", search: "sprite" });
    await client.updateSequence("sequence-1", { name: "walk" });
    for (const call of calls) {
      const headers = new Headers(call.init.headers);
      assert.equal(headers.get("Idempotency-Key"), null);
      assert.equal(headers.get("X-GameKnife-Quote-Id"), null);
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("structured API errors preserve status, code, and user-facing message", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => jsonResponse({ detail: { code: "QUOTE_EXPIRED", message: "报价已过期。" } }, 409);
  try {
    const client = new GameKnifeApiClient({ baseUrl: "https://studio.test" });
    await assert.rejects(
      () => client.createBackgroundRemoveJob("asset-1", {}, submission),
      (error) => error instanceof ApiClientError && error.status === 409 && error.code === "QUOTE_EXPIRED" && error.message === "报价已过期。",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
}

function jobResponse() {
  return {
    id: "job-1",
    type: "background_remove",
    status: "pending",
    input_asset_id: "asset-1",
    parameters: {},
    result: {},
    duration_ms: 0,
    created_at: "2026-08-20T00:00:00Z",
    updated_at: "2026-08-20T00:00:00Z",
  };
}

function assetResponse() {
  return { id: "asset-1", filename: "sprite.png", mime_type: "image/png", size_bytes: 5, url: "/api/assets/asset-1" };
}

function sequenceResponse() {
  return {
    id: "sequence-1",
    name: "walk",
    fps: 12,
    loop: true,
    canvas_width: 64,
    canvas_height: 64,
    anchor_mode: "bottom_center",
    anchor_x: 0.5,
    anchor_y: 1,
    clean_parameters: {},
    status: "ready",
    frame_count: 1,
    enabled_frame_count: 1,
    frames: [],
    warnings: [],
    created_at: "2026-08-20T00:00:00Z",
    updated_at: "2026-08-20T00:00:00Z",
  };
}

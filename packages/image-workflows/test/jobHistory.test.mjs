import assert from "node:assert/strict";
import test from "node:test";
import { readJobRetryRoute } from "../dist/utils/jobRetry.js";

test("failed jobs return to the tool that owns their persisted input", () => {
  assert.equal(readJobRetryRoute(job("background_remove")), "/tools/background-remove");
  assert.equal(readJobRetryRoute(job("sequence_video_to_frames")), "/tools/video-to-sequence");
  assert.equal(readJobRetryRoute(job("project_export_package")), "/assets");
  assert.equal(
    readJobRetryRoute(job("sequence_clean", { sequence_id: "sequence 1" })),
    "/tools/sequence?sequence=sequence%201",
  );
  assert.equal(readJobRetryRoute(job("unknown")), null);
});

function job(type, parameters = {}) {
  return {
    id: "job-1",
    type,
    status: "failed",
    input_asset_id: "asset-1",
    parameters,
    result: {},
    duration_ms: 0,
    created_at: "2026-08-21T00:00:00Z",
    updated_at: "2026-08-21T00:00:00Z",
  };
}

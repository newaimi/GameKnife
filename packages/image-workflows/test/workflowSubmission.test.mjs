import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToString } from "react-dom/server";
import { WorkflowSubmissionProvider, useWorkflowSubmission } from "../dist/context/WorkflowSubmission.js";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

test("the default workflow submission context calls createJob directly without submission options", async () => {
  let captured;
  function Probe() {
    captured = useWorkflowSubmission();
    return null;
  }

  renderToString(createElement(Probe));
  let receivedSubmission = "not-called";
  const expectedJob = { id: "job-1", status: "pending" };
  const result = await captured.submit({
    jobType: "background_remove",
    parameters: { alpha_smoothing: 0 },
    idempotencyPayload: { input_asset_id: "asset-1" },
    createJob: async (submission) => {
      receivedSubmission = submission;
      return expectedJob;
    },
  });

  assert.equal(receivedSubmission, undefined);
  assert.equal(result, expectedJob);
});

test("WorkflowSubmissionProvider exposes an injected implementation to public workspaces", () => {
  let captured;
  const custom = {
    submit: async (request) => request.createJob({ idempotencyKey: "request-1", quoteId: "quote-1" }),
  };
  function Probe() {
    captured = useWorkflowSubmission();
    return null;
  }

  renderToString(createElement(WorkflowSubmissionProvider, { value: custom }, createElement(Probe)));
  assert.equal(captured, custom);
});

test("workspace submission descriptors cover all twelve public job types exactly once", () => {
  const workspaceRoot = resolve(packageRoot, "src/workspaces");
  const files = [
    "background/BackgroundRemoveWorkspace.tsx",
    "upscale/UpscaleWorkspace.tsx",
    "asset-board/AssetBoardWorkspace.tsx",
    "sequence/SequenceWorkspace.tsx",
    "video-generate/VideoGenerateWorkspace.tsx",
    "video-to-sequence/VideoToSequenceWorkspace.tsx",
    "sound-effect/SoundEffectWorkspace.tsx",
  ];
  const jobTypes = files.flatMap((file) => {
    const source = readFileSync(resolve(workspaceRoot, file), "utf8");
    return [...source.matchAll(/jobType:\s*"([a-z_]+)"/g)].map((match) => match[1]);
  });
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
  ]);
  const registrySource = readFileSync(resolve(packageRoot, "../../services/jobs/gameknife_jobs/job_types.py"), "utf8");
  const registered = new Set([...registrySource.matchAll(/job_type="([a-z_]+)"/g)].map((match) => match[1]));

  assert.equal(jobTypes.length, expected.size);
  assert.deepEqual(new Set(jobTypes), expected);
  assert.deepEqual(new Set(jobTypes), registered);
});

test("useWorkflowJob delegates creation and terminal notification to the injected provider", () => {
  const source = readFileSync(resolve(packageRoot, "src/hooks/useWorkflowJob.ts"), "utf8");
  assert.match(source, /submissionProvider\.submit\(\{/);
  assert.match(source, /jobType: options\.jobType/);
  assert.match(source, /parameters: options\.parameters/);
  assert.match(source, /idempotencyPayload: options\.idempotencyPayload/);
  assert.match(source, /submissionProvider\.onJobFinished\?\.\(finished\)/);
});

test("sequence clean submits only client-known parameters", () => {
  const source = readFileSync(resolve(packageRoot, "src/workspaces/sequence/SequenceWorkspace.tsx"), "utf8");
  assert.match(source, /const parameters = \{ sequence_id: sequence\.id, \.\.\.params \}/);
  assert.doesNotMatch(source, /sequence_revision|\brevision\b/);
});

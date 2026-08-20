import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToString } from "react-dom/server";
import ts from "typescript";
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
  assert.match(
    source,
    /catch \(exc\) \{\s*if \(exc instanceof WorkflowSubmissionCancelledError\) \{\s*return null;\s*\}\s*setError/,
  );
  assert.match(source, /finally \{\s*busyRef\.current = false;\s*setBusy\(false\);\s*\}/);
});

test("useWorkflowJob synchronously rejects a same-tick second run and releases the guard after completion", async () => {
  let releaseFirst;
  const firstGate = new Promise((resolve) => {
    releaseFirst = resolve;
  });
  let createCount = 0;
  const workflow = executeUseWorkflowJob({
    waitForJob: async (jobId) => ({ id: jobId, status: "success", result: {} }),
  });
  const options = {
    jobType: "background_remove",
    parameters: { alpha_smoothing: 0 },
    idempotencyPayload: { input_asset_id: "asset-1" },
    failureTitle: "Task failed",
    failureMessage: "Task creation failed.",
    createJob: async () => {
      createCount += 1;
      if (createCount === 1) {
        await firstGate;
      }
      return { id: `job-${createCount}`, status: "pending", result: {} };
    },
  };

  const firstRun = workflow.runJob(options);
  const secondRun = workflow.runJob(options);
  assert.equal(await secondRun, null);
  assert.equal(createCount, 1);

  releaseFirst();
  assert.equal((await firstRun)?.status, "success");
  assert.equal((await workflow.runJob(options))?.status, "success");
  assert.equal(createCount, 2);
});

test("sequence clean submits only client-known parameters", () => {
  const source = readFileSync(resolve(packageRoot, "src/workspaces/sequence/SequenceWorkspace.tsx"), "utf8");
  assert.match(source, /const parameters = \{ sequence_id: sequence\.id, \.\.\.params \}/);
  assert.doesNotMatch(source, /sequence_revision|\brevision\b/);
});

function executeUseWorkflowJob({ waitForJob }) {
  const source = readFileSync(resolve(packageRoot, "src/hooks/useWorkflowJob.ts"), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const module = { exports: {} };
  const submissionProvider = {
    submit: (request) => request.createJob(),
    onJobFinished: () => undefined,
  };
  const react = {
    useCallback: (callback) => callback,
    useRef: (initialValue) => ({ current: initialValue }),
    useState: (initialValue) => [initialValue, () => undefined],
  };
  const requireModule = (specifier) => {
    if (specifier === "react") {
      return react;
    }
    if (specifier === "../context/WorkflowSubmission") {
      return {
        useWorkflowSubmission: () => submissionProvider,
        WorkflowSubmissionCancelledError: class WorkflowSubmissionCancelledError extends Error {},
      };
    }
    if (specifier === "../components/FailureDialog") {
      return {
        readJobFailureDialog: () => null,
        readRequestFailureDialog: () => null,
      };
    }
    if (specifier === "../utils/errors") {
      return { readMessage: (error) => error?.message ?? "request failed" };
    }
    if (specifier === "../utils/jobs") {
      return { waitForJob };
    }
    throw new Error(`Unexpected test dependency: ${specifier}`);
  };

  vm.runInNewContext(compiled, { exports: module.exports, module, require: requireModule });
  return module.exports.useWorkflowJob();
}

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { gameKnifeApiClient } from "@gameknife/api-client";
import type { JobResponse, SequenceCleanParameters, SequenceFrameResponse, SequenceResponse } from "@gameknife/shared-types";
import { ToolWorkspaceLayout } from "../../components/ToolWorkspaceLayout";
import { ImageSequenceUploadAction, WorkbenchActionBar } from "../../components/WorkbenchActionBar";
import { WorkflowFailureDialog } from "../../components/WorkflowFailureDialog";
import { useWorkflowJob, type WorkflowJobRunOptions } from "../../hooks/useWorkflowJob";
import { useWorkflowWritePermission } from "../../hooks/useWorkflowWritePermission";
import { downloadOutputAsset } from "../../utils/assets";
import { readMessage } from "../../utils/errors";
import { JOB_POLLING_PRESETS, readFirstJobOutputAsset } from "../../utils/jobs";
import { openManualEdit } from "../../utils/manualEdit";
import { SequenceEditor } from "./SequenceEditor";

const DEFAULT_SEQUENCE_PARAMS: SequenceCleanParameters = {
  alpha_threshold: 24,
  alpha_smoothing: 0,
  trim_padding: 6,
  canvas_padding: 4,
  denoise: true,
  color_match: true,
  stabilize: false,
  stabilize_strength: 35,
};

type SequenceJobSubmission = Pick<WorkflowJobRunOptions<JobResponse>, "jobType" | "parameters" | "idempotencyPayload" | "createJob">;

export function SequenceWorkspace() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [sequences, setSequences] = useState<SequenceResponse[]>([]);
  const [sequence, setSequence] = useState<SequenceResponse | null>(null);
  const [params, setParams] = useState<SequenceCleanParameters>(DEFAULT_SEQUENCE_PARAMS);
  const [operationBusy, setOperationBusy] = useState(false);
  const { job, busy: jobBusy, error, setError, failureDialog, setFailureDialog, runJob } = useWorkflowJob();
  const canWrite = useWorkflowWritePermission("sequence");
  const busy = operationBusy || jobBusy;
  const requestedSequenceId = searchParams.get("sequence") ?? "";
  const exportAsset = job && ["sequence_export_frames", "sequence_export_spine"].includes(job.type) ? readFirstJobOutputAsset(job) : undefined;

  useEffect(() => {
    void refreshSequences(requestedSequenceId || undefined);
  }, [requestedSequenceId]);

  async function refreshSequences(selectedId?: string) {
    const items = await gameKnifeApiClient.listSequences();
    setSequences(items);
    const nextSelected = selectedId ? items.find((item) => item.id === selectedId) : sequence ? items.find((item) => item.id === sequence.id) : items[0];
    if (nextSelected) {
      await selectSequence(nextSelected.id);
    } else {
      setSequence(null);
    }
  }

  async function importFrames(files: File[]) {
    if (!canWrite) {
      return;
    }
    setOperationBusy(true);
    setError("");
    try {
      const imported = await gameKnifeApiClient.uploadSequenceFrames(files, guessSequenceName(files), 12);
      await refreshSequences(imported.id);
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setOperationBusy(false);
    }
  }

  async function selectSequence(sequenceId: string) {
    const nextSequence = await gameKnifeApiClient.getSequence(sequenceId);
    setSequence(nextSequence);
    setParams(readSequenceCleanParameters(nextSequence));
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set("sequence", sequenceId);
      return next;
    }, { replace: true });
  }

  async function saveSettings(nextSequence: SequenceResponse, nextParams = params) {
    if (!canWrite) {
      return;
    }
    setOperationBusy(true);
    setError("");
    try {
      const updated = await gameKnifeApiClient.updateSequence(nextSequence.id, {
        name: nextSequence.name,
        fps: nextSequence.fps,
        loop: nextSequence.loop,
        canvas_width: nextSequence.canvas_width,
        canvas_height: nextSequence.canvas_height,
        anchor_mode: nextSequence.anchor_mode,
        anchor_x: nextSequence.anchor_x,
        anchor_y: nextSequence.anchor_y,
        clean_parameters: nextParams,
      });
      setSequence(updated);
      await refreshSequences(updated.id);
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setOperationBusy(false);
    }
  }

  async function saveFrames(frames: SequenceFrameResponse[]) {
    if (!sequence || !canWrite) {
      return;
    }
    setOperationBusy(true);
    setError("");
    try {
      const updated = await gameKnifeApiClient.updateSequenceFrames(
        sequence.id,
        frames.map((frame) => ({
          id: frame.id,
          frame_index: frame.frame_index,
          offset_x: frame.offset_x,
          offset_y: frame.offset_y,
          duration_ms: frame.duration_ms,
          enabled: frame.enabled,
        })),
      );
      setSequence(updated);
      await refreshSequences(updated.id);
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setOperationBusy(false);
    }
  }

  async function runSequenceJob(submission: SequenceJobSubmission, refreshAfter = true) {
    if (!canWrite) {
      return;
    }
    const finished = await runJob({
      ...submission,
      failureTitle: "任务创建失败",
      failureMessage: "后端拒绝创建序列帧任务，下面是接口返回的错误内容。",
      polling: JOB_POLLING_PRESETS.standard,
    });
    if (finished?.status === "success" && refreshAfter && sequence) {
      await selectSequence(sequence.id);
      await refreshSequences(sequence.id);
    }
  }

  async function clean() {
    if (!sequence) {
      return;
    }
    const parameters = { sequence_id: sequence.id, ...params };
    await runSequenceJob({
      jobType: "sequence_clean",
      parameters,
      idempotencyPayload: { sequence_id: sequence.id, parameters: params },
      createJob: (submission) => gameKnifeApiClient.createSequenceCleanJob(sequence.id, params, submission),
    });
  }

  async function exportFrames() {
    if (!sequence) {
      return;
    }
    const parameters = { sequence_id: sequence.id, ...params };
    await runSequenceJob({
      jobType: "sequence_export_frames",
      parameters,
      idempotencyPayload: { sequence_id: sequence.id, parameters: params },
      createJob: (submission) => gameKnifeApiClient.createSequenceFramesExportJob(sequence.id, params, submission),
    }, false);
  }

  async function exportSpine() {
    if (!sequence) {
      return;
    }
    const parameters = { sequence_id: sequence.id, ...params };
    await runSequenceJob({
      jobType: "sequence_export_spine",
      parameters,
      idempotencyPayload: { sequence_id: sequence.id, parameters: params },
      createJob: (submission) => gameKnifeApiClient.createSequenceSpineExportJob(sequence.id, params, submission),
    }, false);
  }

  async function deleteSequence(sequenceId: string) {
    if (!canWrite) {
      return;
    }
    setOperationBusy(true);
    setError("");
    try {
      await gameKnifeApiClient.deleteSequence(sequenceId);
      await refreshSequences();
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setOperationBusy(false);
    }
  }

  return (
    <>
      <ToolWorkspaceLayout activeToolId="sequence">
        <SequenceEditor
          sequence={sequence}
          sequences={sequences}
          params={params}
          error={error}
          canWrite={canWrite}
          onSelect={selectSequence}
          onSaveSettings={saveSettings}
          onSaveFrames={saveFrames}
          onParamsChange={setParams}
          onDelete={deleteSequence}
          onManualEdit={openManualEdit}
        />
        <WorkbenchActionBar>
          <ImageSequenceUploadAction label={sequence ? "更换序列" : "上传序列"} disabled={busy || !canWrite} onFiles={importFrames} />
          <button className="primary" type="button" disabled={!sequence || busy || !canWrite} onClick={() => void clean()}>
            {jobBusy ? "处理中" : "清洗"}
          </button>
          <button className="ghost" type="button" disabled={!sequence || busy || !canWrite} onClick={() => void exportFrames()}>
            导出 PNG
          </button>
          <button className="ghost" type="button" disabled={!sequence || busy || !canWrite} onClick={() => void exportSpine()}>
            导出 Spine
          </button>
          <button
            className="ghost"
            type="button"
            disabled={!exportAsset}
            onClick={() =>
              exportAsset
                ? void downloadOutputAsset(exportAsset, job?.type === "sequence_export_spine" ? `${sequence?.name ?? "sequence"}_spine.zip` : `${sequence?.name ?? "sequence"}_frames.zip`)
                : undefined
            }
          >
            下载
          </button>
        </WorkbenchActionBar>
      </ToolWorkspaceLayout>

      <WorkflowFailureDialog failureDialog={failureDialog} onCloseFailure={() => setFailureDialog(null)} />
    </>
  );
}

function readSequenceCleanParameters(sequence: SequenceResponse): SequenceCleanParameters {
  return {
    ...DEFAULT_SEQUENCE_PARAMS,
    ...sequence.clean_parameters,
    denoise: Boolean(sequence.clean_parameters.denoise ?? DEFAULT_SEQUENCE_PARAMS.denoise),
  } as SequenceCleanParameters;
}

function guessSequenceName(files: File[]) {
  const stem = files[0]?.name.replace(/\.[^.]+$/, "") ?? "序列帧";
  return stem.replace(/[_ -]*\d+$/, "").trim() || stem;
}

import { useEffect, useState } from "react";
import { gameKnifeApiClient } from "@gameknife/api-client";
import type { CharacterPartResponse, CharacterRigAnalyzeParameters, CharacterRigResponse, JobResponse } from "@gameknife/shared-types";
import { StatusLine } from "../../components/JobResult";
import { ToolWorkspaceLayout } from "../../components/ToolWorkspaceLayout";
import { ImageUploadStrip } from "../../components/UploadStrip";
import { WorkflowResultFooter } from "../../components/WorkflowResultFooter";
import { useModelRequirement } from "../../hooks/useModelRequirement";
import { useWorkflowDevice } from "../../hooks/useWorkflowDevice";
import { useWorkflowJob } from "../../hooks/useWorkflowJob";
import { useWorkflowWritePermission } from "../../hooks/useWorkflowWritePermission";
import { downloadOutputAsset } from "../../utils/assets";
import { readMessage } from "../../utils/errors";
import { JOB_POLLING_PRESETS, readFirstJobOutputAsset } from "../../utils/jobs";
import { openManualEdit } from "../../utils/manualEdit";
import { CharacterRigEditor } from "./CharacterRigEditor";

const DEFAULT_CHARACTER_RIG_PARAMS: CharacterRigAnalyzeParameters = {
  alpha_threshold: 24,
  overlap_padding: 8,
  box_threshold: 0.25,
  text_threshold: 0.25,
  max_candidates: 16,
  min_mask_area: 96,
  extra_prompts: "",
};

export function CharacterRigWorkspace() {
  const [rig, setRig] = useState<CharacterRigResponse | null>(null);
  const [rigs, setRigs] = useState<CharacterRigResponse[]>([]);
  const [params, setParams] = useState<CharacterRigAnalyzeParameters>(DEFAULT_CHARACTER_RIG_PARAMS);
  const [operationBusy, setOperationBusy] = useState(false);
  const { job, busy: jobBusy, error, setError, failureDialog, setFailureDialog, runJob, resetJob } = useWorkflowJob();
  const device = useWorkflowDevice("character-rig");
  const ensureModelReady = useModelRequirement();
  const canWrite = useWorkflowWritePermission("character-rig");
  const busy = operationBusy || jobBusy;
  const outputAsset = readFirstJobOutputAsset(job);

  useEffect(() => {
    void refreshRigs();
  }, []);

  async function refreshRigs(selectedId?: string) {
    const items = await gameKnifeApiClient.listCharacterRigs();
    setRigs(items);
    if (selectedId) {
      const selected = await gameKnifeApiClient.getCharacterRig(selectedId);
      setRig(selected);
    }
  }

  async function importRig(file: File) {
    if (!canWrite) {
      return;
    }
    setOperationBusy(true);
    setError("");
    try {
      const imported = await gameKnifeApiClient.importCharacterRig(file, file.name.replace(/\.[^.]+$/, "") || "character");
      setRig(imported);
      resetJob();
      await refreshRigs(imported.id);
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setOperationBusy(false);
    }
  }

  async function selectRig(rigId: string) {
    setError("");
    setRig(await gameKnifeApiClient.getCharacterRig(rigId));
  }

  async function saveSettings(nextRig: CharacterRigResponse) {
    if (!canWrite) {
      return;
    }
    setOperationBusy(true);
    setError("");
    try {
      const updated = await gameKnifeApiClient.updateCharacterRig(nextRig.id, {
        name: nextRig.name,
        export_format: nextRig.export_format,
      });
      setRig(updated);
      await refreshRigs(updated.id);
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setOperationBusy(false);
    }
  }

  async function saveParts(parts: CharacterPartResponse[]) {
    if (!rig || !canWrite) {
      return;
    }
    setOperationBusy(true);
    setError("");
    try {
      const updated = await gameKnifeApiClient.updateCharacterParts(
        rig.id,
        parts.map((part) => ({
          id: part.id,
          name: part.name,
          semantic_type: part.semantic_type,
          bbox: part.bbox,
          pivot_x: part.pivot_x,
          pivot_y: part.pivot_y,
          parent_id: part.parent_id,
          z_index: part.z_index,
          enabled: part.enabled,
          needs_completion: part.needs_completion,
        })),
      );
      setRig(updated);
      await refreshRigs(updated.id);
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setOperationBusy(false);
    }
  }

  async function runRigJob(createJob: () => Promise<JobResponse>, refresh = true) {
    if (!rig || !canWrite) {
      return;
    }
    const finished = await runJob({
      createJob,
      failureTitle: "任务创建失败",
      failureMessage: "后端拒绝创建骨骼拆分任务，下面是接口返回的错误内容。",
      polling: JOB_POLLING_PRESETS.long,
    });
    if (finished?.status === "success" && refresh) {
      const updated = await gameKnifeApiClient.getCharacterRig(rig.id);
      setRig(updated);
      await refreshRigs(updated.id);
    }
  }

  async function analyze() {
    if (!rig) {
      return;
    }
    if (!(await ensureModelReady("character-rig"))) {
      return;
    }
    await runRigJob(() => gameKnifeApiClient.createCharacterRigAnalyzeJob(rig.id, params));
  }

  async function refinePart(partId: string, bbox?: [number, number, number, number]) {
    if (!rig) {
      return;
    }
    if (!(await ensureModelReady("character-rig"))) {
      return;
    }
    await runRigJob(() => gameKnifeApiClient.createCharacterPartRefineJob(rig.id, partId, { ...params, bbox }));
  }

  async function exportSpine() {
    if (!rig) {
      return;
    }
    await runRigJob(() => gameKnifeApiClient.createCharacterRigSpineExportJob(rig.id, {}), false);
  }

  async function exportDragonBones() {
    if (!rig) {
      return;
    }
    await runRigJob(() => gameKnifeApiClient.createCharacterRigDragonBonesExportJob(rig.id, {}), false);
  }

  async function deleteRig(rigId: string) {
    if (!canWrite) {
      return;
    }
    setOperationBusy(true);
    setError("");
    try {
      await gameKnifeApiClient.deleteCharacterRig(rigId);
      setRig(null);
      resetJob();
      await refreshRigs();
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setOperationBusy(false);
    }
  }

  return (
    <>
      <ImageUploadStrip
        title={rig ? "已导入角色图" : "导入完整角色图"}
        description="支持完整类人角色设计图，PNG / JPG / WebP"
        disabled={!canWrite}
        onFile={importRig}
      />

      <ToolWorkspaceLayout activeToolId="character-rig">
        <CharacterRigEditor
          rig={rig}
          rigs={rigs}
          params={params}
          currentTask={job}
          canWrite={canWrite}
          device={device}
          onSelect={selectRig}
          onSaveSettings={saveSettings}
          onSaveParts={saveParts}
          onParamsChange={setParams}
          onAnalyze={analyze}
          onRefinePart={refinePart}
          onExportSpine={exportSpine}
          onExportDragonBones={exportDragonBones}
          onDelete={deleteRig}
          onManualEdit={openManualEdit}
        />
      </ToolWorkspaceLayout>

      <WorkflowResultFooter job={job} refreshKey={job?.id ?? rig?.id ?? ""} failureDialog={failureDialog} onCloseFailure={() => setFailureDialog(null)}>
        {outputAsset ? (
          <button className="ghost" type="button" onClick={() => void downloadOutputAsset(outputAsset, `${rig?.name ?? "character-rig"}-export.zip`)}>
            下载导出包
          </button>
        ) : null}
        <StatusLine error={error || (busy ? "处理中" : "")} job={job} />
      </WorkflowResultFooter>
    </>
  );
}

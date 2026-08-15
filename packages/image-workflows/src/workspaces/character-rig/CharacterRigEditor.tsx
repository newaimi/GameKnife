import React, { useEffect, useRef, useState } from "react";
import type { CharacterPartResponse, CharacterRigAnalyzeParameters, CharacterRigResponse, JobResponse } from "@gameknife/shared-types";
import { WorkbenchPreview } from "@gameknife/ui-kit";
import { buildEditedBbox, readImagePointer, type ComponentEditMode, type RigPartEditState } from "../../components/bboxEditing";
import { EmptyCanvas } from "../../components/ImageComparePreview";
import type { ManualEditSource } from "../../types/manualEdit";
import { useObjectUrl } from "../../utils/objectUrl";
import { CharacterRigCanvas } from "./CharacterRigCanvas";
import { CharacterRigInspector } from "./CharacterRigInspector";
import { CharacterRigPartsPanel } from "./CharacterRigPartsPanel";

/**
 * 角色绑定编辑器维护项目草稿、部件草稿和框拖动状态。画布、检查器与部件列表分别渲染，
 * 让坐标编辑链路留在控制器内，同时避免项目表单和结果操作互相持有局部 UI 状态。
 */
export function CharacterRigEditor({
  rig,
  rigs,
  params,
  currentTask,
  canWrite,
  onSelect,
  onSaveSettings,
  onSaveParts,
  onParamsChange,
  onAnalyze,
  onRefinePart,
  onExportSpine,
  onExportDragonBones,
  onDelete,
  onManualEdit,
}: {
  rig: CharacterRigResponse | null;
  rigs: CharacterRigResponse[];
  params: CharacterRigAnalyzeParameters;
  currentTask: JobResponse | null;
  canWrite: boolean;
  onSelect: (rigId: string) => void | Promise<void>;
  onSaveSettings: (rig: CharacterRigResponse) => void | Promise<void>;
  onSaveParts: (parts: CharacterPartResponse[]) => void | Promise<void>;
  onParamsChange: React.Dispatch<React.SetStateAction<CharacterRigAnalyzeParameters>>;
  onAnalyze: () => void | Promise<void>;
  onRefinePart: (partId: string, bbox?: [number, number, number, number]) => void | Promise<void>;
  onExportSpine: () => void | Promise<void>;
  onExportDragonBones: () => void | Promise<void>;
  onDelete: (rigId: string) => void | Promise<void>;
  onManualEdit: (source: Pick<ManualEditSource, "name" | "url" | "sourceFileId" | "sourceContext">) => void | Promise<void>;
}) {
  const [activePartId, setActivePartId] = useState("");
  const [draftRig, setDraftRig] = useState<CharacterRigResponse | null>(rig);
  const [draftParts, setDraftParts] = useState<CharacterPartResponse[]>(rig?.parts ?? []);
  const [activePartEdit, setActivePartEdit] = useState<RigPartEditState | null>(null);
  const rigCanvasRef = useRef<HTMLDivElement>(null);
  const sourceUrl = useObjectUrl(rig?.source_url ?? "");
  const parts = draftParts.slice().sort((first, second) => first.z_index - second.z_index);
  const activePart = parts.find((part) => part.id === activePartId) ?? parts[0] ?? null;
  const activePartUrl = useObjectUrl(activePart?.part_url ?? "");
  const taskRunning = currentTask?.type.startsWith("character_rig_") && ["pending", "running"].includes(currentTask.status);
  const imageSize: [number, number] = [rig?.canvas_width || 1, rig?.canvas_height || 1];

  useEffect(() => {
    setDraftRig(rig);
    setDraftParts(rig?.parts ?? []);
    setActivePartId((current) => {
      if (rig?.parts.some((part) => part.id === current)) return current;
      return rig?.parts[0]?.id ?? "";
    });
  }, [rig?.id, rig?.updated_at]);

  function updatePart(partId: string, patch: Partial<CharacterPartResponse>) {
    setDraftParts((current) => current.map((part) => (part.id === partId ? { ...part, ...patch } : part)));
  }

  useEffect(() => {
    if (!activePartEdit) return;

    const handlePointerMove = (event: PointerEvent) => {
      const frame = rigCanvasRef.current;
      if (!frame) return;
      event.preventDefault();
      const pointer = readImagePointer(event, frame, imageSize);
      updatePart(activePartEdit.partId, { bbox: buildEditedBbox(activePartEdit, pointer, imageSize) });

      const moved =
        activePartEdit.moved || Math.abs(pointer.x - activePartEdit.startPointer.x) > 1 || Math.abs(pointer.y - activePartEdit.startPointer.y) > 1;
      if (moved !== activePartEdit.moved) setActivePartEdit({ ...activePartEdit, moved });
    };

    const handlePointerUp = () => {
      if (activePartEdit.mode === "move" && !activePartEdit.moved) setActivePartId(activePartEdit.partId);
      setActivePartEdit(null);
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp, { once: true });
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [activePartEdit, imageSize[0], imageSize[1]]);

  function startPartEdit(event: React.PointerEvent, part: CharacterPartResponse, mode: ComponentEditMode) {
    const frame = rigCanvasRef.current;
    if (!frame || !canWrite) return;
    event.preventDefault();
    event.stopPropagation();
    // 部件框始终基于按下时的初始框计算，连续状态更新不会反向改变本次拖拽的坐标原点。
    setActivePartEdit({
      partId: part.id,
      mode,
      startBbox: part.bbox,
      startPointer: readImagePointer(event.nativeEvent, frame, imageSize),
      moved: mode !== "move",
    });
  }

  if (!rig || !draftRig) {
    return (
      <>
        <section className="preview-stage character-rig-stage">
          <div className="stage-toolbar">
            <div>
              <h2>骨骼拆分</h2>
              <p>从顶部导入完整角色图后，再生成可确认、可修正、可导出的骨骼部件草稿。</p>
            </div>
          </div>
          <WorkbenchPreview key="character-rig-empty">
            <EmptyCanvas />
          </WorkbenchPreview>
        </section>
        <aside className="settings-panel">
          <h2>骨骼素材</h2>
          <p className="plain-text">当前还没有导入角色图。</p>
        </aside>
      </>
    );
  }

  return (
    <>
      <CharacterRigCanvas
        rig={draftRig}
        sourceUrl={sourceUrl}
        parts={parts}
        activePartId={activePart?.id}
        activePartEdit={activePartEdit}
        canvasRef={rigCanvasRef}
        taskRunning={Boolean(taskRunning)}
        canWrite={canWrite}
        onAnalyze={onAnalyze}
        onSelectPart={setActivePartId}
        onStartPartEdit={startPartEdit}
      />
      <CharacterRigInspector
        rig={rig}
        rigs={rigs}
        draftRig={draftRig}
        parts={parts}
        activePart={activePart}
        params={params}
        taskRunning={Boolean(taskRunning)}
        canWrite={canWrite}
        onSelect={onSelect}
        onDraftRigChange={setDraftRig}
        onParamsChange={onParamsChange}
        onUpdatePart={updatePart}
        onSaveSettings={onSaveSettings}
        onExportSpine={onExportSpine}
        onExportDragonBones={onExportDragonBones}
        onDelete={onDelete}
      />
      <CharacterRigPartsPanel
        parts={parts}
        activePart={activePart}
        activePartUrl={activePartUrl}
        canWrite={canWrite}
        onSelectPart={setActivePartId}
        onUpdatePart={updatePart}
        onRefinePart={onRefinePart}
        onManualEdit={onManualEdit}
        onSaveParts={() => onSaveParts(draftParts)}
      />
    </>
  );
}

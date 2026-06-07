import React, { useEffect, useMemo, useRef, useState } from "react";
import type { CharacterPartResponse, CharacterRigAnalyzeParameters, CharacterRigResponse, JobResponse } from "@gameknife/shared-types";
import { NumberField, WorkbenchPreview } from "@gameknife/ui-kit";
import { useObjectUrl } from "../../utils/objectUrl";
import { EmptyCanvas } from "../../components/ImageComparePreview";
import { buildEditedBbox, readImagePointer, type ComponentEditMode, type RigPartEditState } from "../../components/bboxEditing";
import type { ManualEditSource } from "../../types/manualEdit";

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
  const rigTaskRunning = currentTask?.type.startsWith("character_rig_") && ["pending", "running"].includes(currentTask.status);
  const rigImageSize: [number, number] = [rig?.canvas_width || 1, rig?.canvas_height || 1];

  useEffect(() => {
    setDraftRig(rig);
    setDraftParts(rig?.parts ?? []);
    setActivePartId((current) => {
      if (rig?.parts.some((part) => part.id === current)) return current;
      return rig?.parts[0]?.id ?? "";
    });
  }, [rig?.id, rig?.updated_at]);

  const updatePart = (partId: string, patch: Partial<CharacterPartResponse>) => {
    setDraftParts((current) => current.map((part) => (part.id === partId ? { ...part, ...patch } : part)));
  };

  useEffect(() => {
    if (!activePartEdit) return;

    const handlePointerMove = (event: PointerEvent) => {
      const frame = rigCanvasRef.current;
      if (!frame) return;

      event.preventDefault();
      const pointer = readImagePointer(event, frame, rigImageSize);
      const nextBbox = buildEditedBbox(activePartEdit, pointer, rigImageSize);
      updatePart(activePartEdit.partId, { bbox: nextBbox });

      const moved =
        activePartEdit.moved ||
        Math.abs(pointer.x - activePartEdit.startPointer.x) > 1 ||
        Math.abs(pointer.y - activePartEdit.startPointer.y) > 1;
      if (moved !== activePartEdit.moved) {
        setActivePartEdit({ ...activePartEdit, moved });
      }
    };

    const handlePointerUp = () => {
      if (activePartEdit.mode === "move" && !activePartEdit.moved) {
        setActivePartId(activePartEdit.partId);
      }
      setActivePartEdit(null);
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp, { once: true });
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [activePartEdit, rigImageSize[0], rigImageSize[1]]);

  const startPartEdit = (event: React.PointerEvent, part: CharacterPartResponse, mode: ComponentEditMode) => {
    const frame = rigCanvasRef.current;
    if (!frame || !canWrite) return;

    event.preventDefault();
    event.stopPropagation();
    // 部件框编辑沿用素材板的“按初始框计算”策略，避免拖拽过程中连续状态更新造成框体漂移。
    setActivePartEdit({
      partId: part.id,
      mode,
      startBbox: part.bbox,
      startPointer: readImagePointer(event.nativeEvent, frame, rigImageSize),
      moved: mode !== "move",
    });
  };

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
      <section className="preview-stage character-rig-stage">
        <div className="stage-toolbar">
          <div>
            <h2>骨骼拆分</h2>
            <p>
              {draftRig.part_count} 个部件 · {draftRig.canvas_width}×{draftRig.canvas_height} · {draftRig.status}
            </p>
          </div>
        <div className="toolbar-actions">
          <button className="primary" type="button" disabled={rigTaskRunning || !canWrite} onClick={() => void onAnalyze()}>
              {rigTaskRunning ? "处理中..." : "智能候选拆分"}
            </button>
          </div>
        </div>

        <WorkbenchPreview key={`character-rig-${rig.id}`}>
          <div className="rig-canvas" ref={rigCanvasRef} style={{ width: rig.canvas_width || 420, height: rig.canvas_height || 420 }}>
            {sourceUrl ? <img className="rig-source-image" src={sourceUrl} alt={rig.name} /> : <span>正在加载角色图...</span>}
            {parts.map((part) => (
              <div
                key={part.id}
                role="button"
                tabIndex={0}
                className={`rig-part-box no-pan ${part.id === activePart?.id ? "active" : ""} ${part.needs_completion ? "needs-completion" : ""} ${
                  activePartEdit?.partId === part.id ? "editing" : ""
                }`}
                style={{ left: part.bbox[0], top: part.bbox[1], width: part.bbox[2], height: part.bbox[3] }}
                onPointerDown={(event) => startPartEdit(event, part, "move")}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setActivePartId(part.id);
                  }
                }}
              >
                <span>{part.name}</span>
                <i style={{ left: `${part.pivot_x * 100}%`, top: `${part.pivot_y * 100}%` }} />
                <b className="resize-handle nw" onPointerDown={(event) => startPartEdit(event, part, "nw")} />
                <b className="resize-handle ne" onPointerDown={(event) => startPartEdit(event, part, "ne")} />
                <b className="resize-handle sw" onPointerDown={(event) => startPartEdit(event, part, "sw")} />
                <b className="resize-handle se" onPointerDown={(event) => startPartEdit(event, part, "se")} />
              </div>
            ))}
          </div>
        </WorkbenchPreview>
      </section>

      <aside className="settings-panel character-rig-settings">
        <h2>项目设置</h2>
        <label className="number-field">
          <span>当前项目</span>
          <select value={rig.id} onChange={(event) => void onSelect(event.target.value)}>
            {rigs.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label className="number-field">
          <span>名称</span>
          <input value={draftRig.name} onChange={(event) => setDraftRig({ ...draftRig, name: event.target.value })} />
        </label>
        <NumberField label="画布宽" value={draftRig.canvas_width} min={0} max={8192} onChange={(canvas_width) => setDraftRig({ ...draftRig, canvas_width })} />
        <NumberField label="画布高" value={draftRig.canvas_height} min={0} max={8192} onChange={(canvas_height) => setDraftRig({ ...draftRig, canvas_height })} />

        <h2>拆分参数</h2>
        <NumberField label="Alpha 阈值" value={params.alpha_threshold} min={0} max={255} onChange={(value) => onParamsChange((current) => ({ ...current, alpha_threshold: value }))} />
        <NumberField label="Overlap 扩边" value={params.overlap_padding} min={0} max={80} onChange={(value) => onParamsChange((current) => ({ ...current, overlap_padding: value }))} />
        <NumberField label="框置信度" value={Math.round(params.box_threshold * 100)} min={1} max={95} onChange={(value) => onParamsChange((current) => ({ ...current, box_threshold: value / 100 }))} />
        <NumberField label="文本置信度" value={Math.round(params.text_threshold * 100)} min={1} max={95} onChange={(value) => onParamsChange((current) => ({ ...current, text_threshold: value / 100 }))} />
        <NumberField label="候选上限" value={params.max_candidates} min={1} max={40} onChange={(value) => onParamsChange((current) => ({ ...current, max_candidates: value }))} />
        <NumberField label="最小面积" value={params.min_mask_area} min={1} max={100000} onChange={(value) => onParamsChange((current) => ({ ...current, min_mask_area: value }))} />
        <label className="number-field">
          <span>补充候选词</span>
          <textarea
            value={params.extra_prompts}
            onChange={(event) => onParamsChange((current) => ({ ...current, extra_prompts: event.target.value }))}
            placeholder="例如：helmet, axe, tail"
          />
        </label>

        {activePart ? (
          <>
            <h2>当前部件</h2>
            <label className="number-field">
              <span>名称</span>
              <input value={activePart.name} onChange={(event) => updatePart(activePart.id, { name: event.target.value })} />
            </label>
            <label className="number-field">
              <span>父骨骼</span>
              <select value={activePart.parent_id ?? ""} onChange={(event) => updatePart(activePart.id, { parent_id: event.target.value || null })}>
                <option value="">root</option>
                {parts
                  .filter((part) => part.id !== activePart.id)
                  .map((part) => (
                    <option key={part.id} value={part.id}>
                      {part.name}
                    </option>
                  ))}
              </select>
            </label>
            <NumberField label="Pivot X" value={Math.round(activePart.pivot_x * 100)} min={0} max={100} onChange={(value) => updatePart(activePart.id, { pivot_x: value / 100 })} />
            <NumberField label="Pivot Y" value={Math.round(activePart.pivot_y * 100)} min={0} max={100} onChange={(value) => updatePart(activePart.id, { pivot_y: value / 100 })} />
            <NumberField label="图层顺序" value={activePart.z_index} min={-1000} max={1000} onChange={(z_index) => updatePart(activePart.id, { z_index })} />
          </>
        ) : null}

        <button className="primary install-button" type="button" disabled={!canWrite} onClick={() => void onSaveSettings(draftRig)}>
          保存项目
        </button>
        <div className="export-stack">
          <button className="ghost" type="button" disabled={rigTaskRunning || !parts.length || !canWrite} onClick={() => void onExportSpine()}>
            导出 Spine
          </button>
          <button className="ghost" type="button" disabled={rigTaskRunning || !parts.length || !canWrite} onClick={() => void onExportDragonBones()}>
            导出 DragonBones
          </button>
          <button className="ghost danger-text" type="button" disabled={!canWrite} onClick={() => void onDelete(rig.id)}>
            删除项目
          </button>
        </div>
      </aside>

      {parts.length ? (
        <section className="workspace-result-panel character-rig-result-panel">
          {activePart ? (
            <div className="frame-editor rig-editor">
              <strong>{activePart.name}</strong>
              {activePartUrl ? <img className="rig-part-preview" src={activePartUrl} alt={activePart.name} /> : null}
              <button className="ghost compact" type="button" disabled={!canWrite} onClick={() => updatePart(activePart.id, { enabled: !activePart.enabled })}>
                {activePart.enabled ? "停用部件" : "启用部件"}
              </button>
              <button className="ghost compact" type="button" disabled={!canWrite} onClick={() => updatePart(activePart.id, { needs_completion: !activePart.needs_completion })}>
                {activePart.needs_completion ? "取消补全标记" : "标记需补全"}
              </button>
              <button className="ghost compact" type="button" disabled={!canWrite} onClick={() => void onRefinePart(activePart.id, activePart.bbox)}>
                精修部件
              </button>
              <button
                className="ghost compact"
                type="button"
                disabled={!activePartUrl || !canWrite}
                onClick={() =>
                  activePartUrl
                    ? void onManualEdit({
                        name: `${activePart.name}.png`,
                        url: activePartUrl,
                        sourceFileId: activePart.part_asset_id ?? undefined,
                        sourceContext: "character_part",
                      })
                    : undefined
                }
              >
                编辑部件
              </button>
              <button className="primary compact" type="button" disabled={!canWrite} onClick={() => void onSaveParts(draftParts)}>
                保存部件
              </button>
            </div>
          ) : null}

          <div className="rig-parts-grid">
            {parts.map((part) => (
              <button
                key={part.id}
                className={`rig-part-card ${part.id === activePart?.id ? "active" : ""} ${part.enabled ? "" : "disabled"}`}
                type="button"
                onClick={() => setActivePartId(part.id)}
              >
                <span>{part.name}</span>
                <small>{part.semantic_type}</small>
                {part.needs_completion ? <em>需补全</em> : null}
              </button>
            ))}
          </div>
        </section>
      ) : null}
    </>
  );
}


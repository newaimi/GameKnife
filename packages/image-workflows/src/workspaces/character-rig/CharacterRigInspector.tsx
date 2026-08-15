import type { Dispatch, SetStateAction } from "react";
import type { CharacterPartResponse, CharacterRigAnalyzeParameters, CharacterRigResponse } from "@gameknife/shared-types";
import { Button, NumberField } from "@gameknife/ui-kit";

export function CharacterRigInspector({
  rig,
  rigs,
  draftRig,
  parts,
  activePart,
  params,
  taskRunning,
  canWrite,
  onSelect,
  onDraftRigChange,
  onParamsChange,
  onUpdatePart,
  onSaveSettings,
  onExportSpine,
  onExportDragonBones,
  onDelete,
}: {
  rig: CharacterRigResponse;
  rigs: CharacterRigResponse[];
  draftRig: CharacterRigResponse;
  parts: CharacterPartResponse[];
  activePart: CharacterPartResponse | null;
  params: CharacterRigAnalyzeParameters;
  taskRunning: boolean;
  canWrite: boolean;
  onSelect: (rigId: string) => void | Promise<void>;
  onDraftRigChange: (rig: CharacterRigResponse) => void;
  onParamsChange: Dispatch<SetStateAction<CharacterRigAnalyzeParameters>>;
  onUpdatePart: (partId: string, patch: Partial<CharacterPartResponse>) => void;
  onSaveSettings: (rig: CharacterRigResponse) => void | Promise<void>;
  onExportSpine: () => void | Promise<void>;
  onExportDragonBones: () => void | Promise<void>;
  onDelete: (rigId: string) => void | Promise<void>;
}) {
  return (
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
        <input value={draftRig.name} onChange={(event) => onDraftRigChange({ ...draftRig, name: event.target.value })} />
      </label>
      <NumberField label="画布宽" value={draftRig.canvas_width} min={0} max={8192} onChange={(canvas_width) => onDraftRigChange({ ...draftRig, canvas_width })} />
      <NumberField label="画布高" value={draftRig.canvas_height} min={0} max={8192} onChange={(canvas_height) => onDraftRigChange({ ...draftRig, canvas_height })} />

      <h2>拆分参数</h2>
      <NumberField label="Alpha 阈值" value={params.alpha_threshold} min={0} max={255} onChange={(value) => onParamsChange((current) => ({ ...current, alpha_threshold: value }))} />
      <NumberField label="Overlap 扩边" value={params.overlap_padding} min={0} max={80} onChange={(value) => onParamsChange((current) => ({ ...current, overlap_padding: value }))} />
      <NumberField label="框置信度" value={Math.round(params.box_threshold * 100)} min={1} max={95} onChange={(value) => onParamsChange((current) => ({ ...current, box_threshold: value / 100 }))} />
      <NumberField label="文本置信度" value={Math.round(params.text_threshold * 100)} min={1} max={95} onChange={(value) => onParamsChange((current) => ({ ...current, text_threshold: value / 100 }))} />
      <NumberField label="候选上限" value={params.max_candidates} min={1} max={40} onChange={(value) => onParamsChange((current) => ({ ...current, max_candidates: value }))} />
      <NumberField label="最小面积" value={params.min_mask_area} min={1} max={100000} onChange={(value) => onParamsChange((current) => ({ ...current, min_mask_area: value }))} />
      <label className="number-field">
        <span>补充候选词</span>
        <textarea value={params.extra_prompts} onChange={(event) => onParamsChange((current) => ({ ...current, extra_prompts: event.target.value }))} placeholder="例如：helmet, axe, tail" />
      </label>

      {activePart ? (
        <>
          <h2>当前部件</h2>
          <label className="number-field">
            <span>名称</span>
            <input value={activePart.name} onChange={(event) => onUpdatePart(activePart.id, { name: event.target.value })} />
          </label>
          <label className="number-field">
            <span>父骨骼</span>
            <select value={activePart.parent_id ?? ""} onChange={(event) => onUpdatePart(activePart.id, { parent_id: event.target.value || null })}>
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
          <NumberField label="Pivot X" value={Math.round(activePart.pivot_x * 100)} min={0} max={100} onChange={(value) => onUpdatePart(activePart.id, { pivot_x: value / 100 })} />
          <NumberField label="Pivot Y" value={Math.round(activePart.pivot_y * 100)} min={0} max={100} onChange={(value) => onUpdatePart(activePart.id, { pivot_y: value / 100 })} />
          <NumberField label="图层顺序" value={activePart.z_index} min={-1000} max={1000} onChange={(z_index) => onUpdatePart(activePart.id, { z_index })} />
        </>
      ) : null}

      <Button className="install-button" variant="primary" disabled={!canWrite} onClick={() => void onSaveSettings(draftRig)}>
        保存项目
      </Button>
      <div className="export-stack">
        <Button disabled={taskRunning || !parts.length || !canWrite} onClick={() => void onExportSpine()}>
          导出 Spine
        </Button>
        <Button disabled={taskRunning || !parts.length || !canWrite} onClick={() => void onExportDragonBones()}>
          导出 DragonBones
        </Button>
        <Button variant="danger" disabled={!canWrite} onClick={() => void onDelete(rig.id)}>
          删除项目
        </Button>
      </div>
    </aside>
  );
}

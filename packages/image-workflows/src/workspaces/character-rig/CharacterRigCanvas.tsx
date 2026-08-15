import type { RefObject } from "react";
import type { CharacterPartResponse, CharacterRigResponse } from "@gameknife/shared-types";
import { Button, WorkbenchPreview } from "@gameknife/ui-kit";
import type { ComponentEditMode, RigPartEditState } from "../../components/bboxEditing";

export function CharacterRigCanvas({
  rig,
  sourceUrl,
  parts,
  activePartId,
  activePartEdit,
  canvasRef,
  taskRunning,
  canWrite,
  onAnalyze,
  onSelectPart,
  onStartPartEdit,
}: {
  rig: CharacterRigResponse;
  sourceUrl: string;
  parts: CharacterPartResponse[];
  activePartId?: string;
  activePartEdit: RigPartEditState | null;
  canvasRef: RefObject<HTMLDivElement | null>;
  taskRunning: boolean;
  canWrite: boolean;
  onAnalyze: () => void | Promise<void>;
  onSelectPart: (partId: string) => void;
  onStartPartEdit: (event: React.PointerEvent, part: CharacterPartResponse, mode: ComponentEditMode) => void;
}) {
  return (
    <section className="preview-stage character-rig-stage">
      <div className="stage-toolbar">
        <div>
          <h2>骨骼拆分</h2>
          <p>
            {parts.length} 个部件 · {rig.canvas_width}×{rig.canvas_height} · {rig.status}
          </p>
        </div>
        <div className="toolbar-actions">
          <Button variant="primary" disabled={taskRunning || !canWrite} onClick={() => void onAnalyze()}>
            {taskRunning ? "处理中..." : "智能候选拆分"}
          </Button>
        </div>
      </div>

      <WorkbenchPreview key={`character-rig-${rig.id}`}>
        <div className="rig-canvas" ref={canvasRef} style={{ width: rig.canvas_width || 420, height: rig.canvas_height || 420 }}>
          {sourceUrl ? <img className="rig-source-image" src={sourceUrl} alt={rig.name} /> : <span>正在加载角色图...</span>}
          {parts.map((part) => (
            <div
              key={part.id}
              role="button"
              tabIndex={0}
              className={`rig-part-box no-pan ${part.id === activePartId ? "active" : ""} ${part.needs_completion ? "needs-completion" : ""} ${
                activePartEdit?.partId === part.id ? "editing" : ""
              }`}
              style={{ left: part.bbox[0], top: part.bbox[1], width: part.bbox[2], height: part.bbox[3] }}
              onPointerDown={(event) => onStartPartEdit(event, part, "move")}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelectPart(part.id);
                }
              }}
            >
              <span>{part.name}</span>
              <i style={{ left: `${part.pivot_x * 100}%`, top: `${part.pivot_y * 100}%` }} />
              <b className="resize-handle nw" onPointerDown={(event) => onStartPartEdit(event, part, "nw")} />
              <b className="resize-handle ne" onPointerDown={(event) => onStartPartEdit(event, part, "ne")} />
              <b className="resize-handle sw" onPointerDown={(event) => onStartPartEdit(event, part, "sw")} />
              <b className="resize-handle se" onPointerDown={(event) => onStartPartEdit(event, part, "se")} />
            </div>
          ))}
        </div>
      </WorkbenchPreview>
    </section>
  );
}

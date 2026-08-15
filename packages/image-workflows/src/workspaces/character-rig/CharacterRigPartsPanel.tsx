import type { CharacterPartResponse } from "@gameknife/shared-types";
import { Button } from "@gameknife/ui-kit";
import type { ManualEditSource } from "../../types/manualEdit";

export function CharacterRigPartsPanel({
  parts,
  activePart,
  activePartUrl,
  canWrite,
  onSelectPart,
  onUpdatePart,
  onRefinePart,
  onManualEdit,
  onSaveParts,
}: {
  parts: CharacterPartResponse[];
  activePart: CharacterPartResponse | null;
  activePartUrl: string;
  canWrite: boolean;
  onSelectPart: (partId: string) => void;
  onUpdatePart: (partId: string, patch: Partial<CharacterPartResponse>) => void;
  onRefinePart: (partId: string, bbox?: [number, number, number, number]) => void | Promise<void>;
  onManualEdit: (source: Pick<ManualEditSource, "name" | "url" | "sourceFileId" | "sourceContext">) => void | Promise<void>;
  onSaveParts: () => void | Promise<void>;
}) {
  if (!parts.length) return null;

  return (
    <section className="workspace-result-panel character-rig-result-panel">
      {activePart ? (
        <div className="frame-editor rig-editor">
          <strong>{activePart.name}</strong>
          {activePartUrl ? <img className="rig-part-preview" src={activePartUrl} alt={activePart.name} /> : null}
          <Button size="small" disabled={!canWrite} onClick={() => onUpdatePart(activePart.id, { enabled: !activePart.enabled })}>
            {activePart.enabled ? "停用部件" : "启用部件"}
          </Button>
          <Button size="small" disabled={!canWrite} onClick={() => onUpdatePart(activePart.id, { needs_completion: !activePart.needs_completion })}>
            {activePart.needs_completion ? "取消补全标记" : "标记需补全"}
          </Button>
          <Button size="small" disabled={!canWrite} onClick={() => void onRefinePart(activePart.id, activePart.bbox)}>
            精修部件
          </Button>
          <Button
            size="small"
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
          </Button>
          <Button size="small" variant="primary" disabled={!canWrite} onClick={() => void onSaveParts()}>
            保存部件
          </Button>
        </div>
      ) : null}

      <div className="rig-parts-grid">
        {parts.map((part) => (
          <button
            key={part.id}
            className={`rig-part-card ${part.id === activePart?.id ? "active" : ""} ${part.enabled ? "" : "disabled"}`}
            type="button"
            aria-pressed={part.id === activePart?.id}
            onClick={() => onSelectPart(part.id)}
          >
            <span>{part.name}</span>
            <small>{part.semantic_type}</small>
            {part.needs_completion ? <em>需补全</em> : null}
          </button>
        ))}
      </div>
    </section>
  );
}

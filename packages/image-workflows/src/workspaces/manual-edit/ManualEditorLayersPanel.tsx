import { useEffect, useRef, useState, type RefObject } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronUp, Eye, EyeOff, Trash2 } from "lucide-react";
import { Button, IconButton } from "@gameknife/ui-kit";
import type { EditorStatus, ManualEditorHandle } from "./types";

/**
 * Keeps layer name and opacity drafts local until they are committed to editor history. Local drafts avoid
 * rebuilding the canvas controller on each keystroke and keep the page controller focused on cross-panel state.
 */
export function ManualEditorLayersPanel({
  editorRef,
  status,
  hasSource,
}: {
  editorRef: RefObject<ManualEditorHandle | null>;
  status: EditorStatus;
  hasSource: boolean;
}) {
  const { t } = useTranslation("manualEditor");
  const skipNameCommitRef = useRef<Set<string>>(new Set());
  const [nameDrafts, setNameDrafts] = useState<Record<string, string>>({});
  const [opacityDrafts, setOpacityDrafts] = useState<Record<string, number>>({});

  useEffect(() => {
    const layerMap = new Map(status.layers.map((layer) => [layer.id, layer]));
    setNameDrafts((current) => filterSettledDrafts(current, layerMap, (layer) => layer.name));
    setOpacityDrafts((current) => filterSettledDrafts(current, layerMap, (layer) => layer.opacity));
  }, [status.layers]);

  function commitName(layerId: string, currentName: string) {
    const draftName = nameDrafts[layerId];
    if (draftName === undefined) return;
    const nextName = draftName.trim() || t("layers.defaultName");
    if (nextName !== currentName) editorRef.current?.updateLayerName(layerId, nextName);
    discardName(layerId);
  }

  function discardName(layerId: string) {
    setNameDrafts((current) => omitDraft(current, layerId));
  }

  function previewOpacity(layerId: string, opacity: number) {
    const nextOpacity = Math.min(Math.max(Math.round(opacity), 0), 100);
    setOpacityDrafts((current) => ({ ...current, [layerId]: nextOpacity }));
    editorRef.current?.previewLayerOpacity(layerId, nextOpacity);
  }

  function commitOpacity(layerId: string) {
    editorRef.current?.commitLayerOpacity(layerId);
    setOpacityDrafts((current) => omitDraft(current, layerId));
  }

  return (
    <div className="editor-section">
      <strong>{t("layers.title")}</strong>
      <div className="editor-action-row">
        <Button size="small" disabled={!hasSource} onClick={() => editorRef.current?.createLayer()}>
          {t("layers.create")}
        </Button>
        <Button size="small" disabled={!status.activeLayerId} onClick={() => editorRef.current?.duplicateLayer()}>
          {t("layers.duplicate")}
        </Button>
        <Button size="small" disabled={!status.activeLayerId} onClick={() => status.activeLayerId && editorRef.current?.mergeLayerDown(status.activeLayerId)}>
          {t("layers.mergeDown")}
        </Button>
        <Button size="small" disabled={!status.activeLayerId} onClick={() => editorRef.current?.flattenLayers()}>
          {t("layers.flatten")}
        </Button>
      </div>
      <div className="editor-layer-list">
        {status.layers.length ? (
          status.layers.map((layer) => (
            <div className={`editor-layer-row ${layer.active ? "active" : ""}`} key={layer.id}>
              <IconButton label={layer.visible ? t("layers.hide") : t("layers.show")} onClick={() => editorRef.current?.toggleLayerVisibility(layer.id)}>
                {layer.visible ? <Eye size={15} /> : <EyeOff size={15} />}
              </IconButton>
              <input
                type="text"
                value={nameDrafts[layer.id] ?? layer.name}
                aria-label={t("layers.name", { name: layer.name })}
                onFocus={() => editorRef.current?.setActiveLayer(layer.id)}
                onChange={(event) => setNameDrafts((current) => ({ ...current, [layer.id]: event.target.value }))}
                onBlur={() => {
                  if (skipNameCommitRef.current.has(layer.id)) {
                    skipNameCommitRef.current.delete(layer.id);
                    return;
                  }
                  commitName(layer.id, layer.name);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    event.currentTarget.blur();
                  }
                  if (event.key === "Escape") {
                    event.preventDefault();
                    skipNameCommitRef.current.add(layer.id);
                    discardName(layer.id);
                    event.currentTarget.blur();
                  }
                }}
              />
              <IconButton label={t("layers.moveUp")} onClick={() => editorRef.current?.moveLayer(layer.id, "up")}>
                <ChevronUp size={15} />
              </IconButton>
              <IconButton label={t("layers.moveDown")} onClick={() => editorRef.current?.moveLayer(layer.id, "down")}>
                <ChevronDown size={15} />
              </IconButton>
              <IconButton label={t("layers.delete")} variant="danger" onClick={() => editorRef.current?.deleteLayer(layer.id)}>
                <Trash2 size={15} />
              </IconButton>
              <label>
                <span>{t("layers.opacity")}</span>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={opacityDrafts[layer.id] ?? layer.opacity}
                  onChange={(event) => previewOpacity(layer.id, Number(event.target.value))}
                  onPointerUp={() => commitOpacity(layer.id)}
                  onBlur={() => commitOpacity(layer.id)}
                />
              </label>
            </div>
          ))
        ) : (
          <p className="helper-text">{t("layers.empty")}</p>
        )}
      </div>
    </div>
  );
}

function omitDraft<T>(drafts: Record<string, T>, id: string) {
  const next = { ...drafts };
  delete next[id];
  return next;
}

function filterSettledDrafts<T>(
  drafts: Record<string, T>,
  layers: Map<string, EditorStatus["layers"][number]>,
  readValue: (layer: EditorStatus["layers"][number]) => T,
) {
  let changed = false;
  const next: Record<string, T> = {};
  Object.entries(drafts).forEach(([layerId, draft]) => {
    const layer = layers.get(layerId);
    if (!layer || readValue(layer) === draft) {
      changed = true;
      return;
    }
    next[layerId] = draft;
  });
  return changed ? next : drafts;
}

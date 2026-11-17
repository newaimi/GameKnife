import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Play, RefreshCw } from "lucide-react";
import { gameKnifeApiClient } from "@gameknife/api-client";
import type { AssetBoardParameters, ComponentCandidate, JobResponse } from "@gameknife/shared-types";
import { NumberField, WorkbenchPreview } from "@gameknife/ui-kit";
import { AssetBoardPreview, cloneComponent } from "../../components/AssetBoardPreview";
import { EmptyCanvas } from "../../components/ImageComparePreview";
import { StatusLine } from "../../components/StatusLine";
import { ToolWorkspaceLayout } from "../../components/ToolWorkspaceLayout";
import { ImageUploadAction, WorkbenchActionBar } from "../../components/WorkbenchActionBar";
import { WorkflowFailureDialog } from "../../components/WorkflowFailureDialog";
import { useImageAssetUpload } from "../../hooks/useImageAssetUpload";
import { useModelRequirement } from "../../hooks/useModelRequirement";
import { useWorkflowJob, type WorkflowJobRunOptions } from "../../hooks/useWorkflowJob";
import { useWorkflowWritePermission } from "../../hooks/useWorkflowWritePermission";
import { downloadOutputAsset } from "../../utils/assets";
import { JOB_POLLING_PRESETS, readFirstJobOutputAsset, readString, readTupleNumber } from "../../utils/jobs";
import { openManualEdit } from "../../utils/manualEdit";

const DEFAULT_ASSET_BOARD_PARAMS: AssetBoardParameters = {
  alpha_threshold: 16,
  min_component_area: 500,
  alpha_smoothing: 0,
  alpha_contract: 0,
  alpha_feather: 0,
  alpha_defringe: 0,
  export_padding: 8,
};

type AssetBoardJobSubmission = Pick<WorkflowJobRunOptions<JobResponse>, "jobType" | "parameters" | "idempotencyPayload" | "createJob">;

export function AssetBoardWorkspace() {
  const { t } = useTranslation("workflows");
  const { t: tWorkbench } = useTranslation("workbench");
  const [params, setParams] = useState<AssetBoardParameters>(DEFAULT_ASSET_BOARD_PARAMS);
  const [components, setComponents] = useState<ComponentCandidate[]>([]);
  const [selectedComponents, setSelectedComponents] = useState<Set<number>>(new Set());
  const [imageSize, setImageSize] = useState<[number, number] | undefined>();
  const [cutoutAssetId, setCutoutAssetId] = useState("");
  const [cutoutUrl, setCutoutUrl] = useState("");
  const [compare, setCompare] = useState(50);
  const lastAutomaticRegionSignature = useRef("");
  const { job, busy: jobBusy, error: jobError, setError, failureDialog, setFailureDialog, runJob: runWorkflowJob, resetJob } = useWorkflowJob();
  const ensureModelReady = useModelRequirement();
  const canWrite = useWorkflowWritePermission("asset-board");
  const { asset, upload, uploading, uploadError } = useImageAssetUpload({
    onBeforeUpload: () => {
      resetJob();
      setComponents([]);
      setSelectedComponents(new Set());
      setImageSize(undefined);
      setCutoutAssetId("");
      setCutoutUrl("");
      setCompare(50);
    },
  });
  const busy = uploading || jobBusy;
  const error = uploadError || jobError;
  const selectedCount = selectedComponents.size;
  const exportAsset = job?.type === "asset_board_export" ? readFirstJobOutputAsset(job) : undefined;

  useEffect(() => {
    if (!asset || busy || !canWrite) {
      return;
    }

    const regionSignature = `${asset.id}:${params.alpha_threshold}:${params.min_component_area}:${cutoutAssetId || "source"}`;
    if (lastAutomaticRegionSignature.current === regionSignature) {
      return;
    }

    const timer = window.setTimeout(() => {
      lastAutomaticRegionSignature.current = regionSignature;
      if (cutoutAssetId) {
        void refine();
        return;
      }
      void detectRegions();
    }, 300);

    return () => window.clearTimeout(timer);
  }, [asset, busy, canWrite, cutoutAssetId, params.alpha_threshold, params.min_component_area]);

  async function detectRegions() {
    if (!asset || !canWrite) {
      return;
    }
    // Region detection is a lightweight CPU step and refreshes after upload or region parameter changes.
    // Only threshold and minimum area trigger it so edge cleanup cannot create model jobs implicitly.
    const parameters = readRegionParameters();
    await runJob({
      jobType: "asset_board_region_detect",
      parameters,
      idempotencyPayload: { input_asset_id: asset.id, parameters },
      createJob: (submission) => gameKnifeApiClient.createAssetBoardRegionJob(asset.id, parameters, submission),
    }, applyComponentJobResult);
  }

  async function cutout() {
    if (!asset || !canWrite) {
      return;
    }
    if (!(await ensureModelReady("birefnet"))) {
      return;
    }
    const parameters = { ...params };
    await runJob({
      jobType: "asset_board_cutout",
      parameters,
      idempotencyPayload: { input_asset_id: asset.id, parameters },
      createJob: (submission) => gameKnifeApiClient.createAssetBoardCutoutJob(asset.id, parameters, submission),
    }, applyCutoutJobResult);
  }

  async function refine() {
    if (!canWrite) {
      return;
    }
    if (!cutoutAssetId) {
      setError(t("assetBoard.cutoutRequired"));
      return;
    }
    const parameters = readRegionParameters();
    await runJob({
      jobType: "asset_board_region_refine",
      parameters,
      idempotencyPayload: { cutout_asset_id: cutoutAssetId, parameters },
      createJob: (submission) => gameKnifeApiClient.createAssetBoardRefineJob(cutoutAssetId, parameters, submission),
    }, applyComponentJobResult);
  }

  async function exportSelected() {
    if (!canWrite) {
      return;
    }
    if (!cutoutAssetId) {
      setError(t("assetBoard.cutoutRequired"));
      return;
    }
    const selectedComponentIds = Array.from(selectedComponents);
    const exportParameters = { ...params };
    const parameters = { ...exportParameters, selected_component_ids: selectedComponentIds, components };
    await runJob({
      jobType: "asset_board_export",
      parameters,
      idempotencyPayload: {
        cutout_asset_id: cutoutAssetId,
        selected_component_ids: selectedComponentIds,
        components,
        parameters: exportParameters,
      },
      createJob: (submission) => gameKnifeApiClient.createAssetBoardExportJob({
        cutoutAssetId,
        selectedComponentIds,
        components,
        parameters: exportParameters,
      }, submission),
    });
  }

  async function runJob(submission: AssetBoardJobSubmission, onSuccess?: (finished: JobResponse) => void) {
    await runWorkflowJob({
      ...submission,
      failureTitle: t("common.jobCreationFailed"),
      failureMessage: t("common.backendRejected", { workflow: t("assetBoard.workflow") }),
      polling: JOB_POLLING_PRESETS.standard,
      onSuccess,
    });
  }

  function applyCutoutJobResult(finished: JobResponse) {
    const nextCutoutAssetId = readString(finished.result.cutout_asset_id);
    const nextCutoutUrl = readString(finished.result.cutout_url);
    setCutoutAssetId(nextCutoutAssetId);
    setCutoutUrl(nextCutoutUrl);
    const nextImageSize = readTupleNumber(finished.result.image_size);
    if (nextImageSize) {
      setImageSize(nextImageSize);
    }
  }

  function applyComponentJobResult(finished: JobResponse) {
    const nextComponents = readComponents(finished.result.components);
    const nextImageSize = readTupleNumber(finished.result.image_size);
    const nextCutoutAssetId = readString(finished.result.cutout_asset_id);
    const nextCutoutUrl = readString(finished.result.cutout_url);
    const previousById = new Map(components.map((component) => [component.id, component]));
    const mergedComponents = nextComponents.map((component) => {
      const previous = previousById.get(component.id);
      return previous
        ? {
            ...component,
            name: previous.name,
            state: previous.state,
            nine_slice: normalizeNineSlice(previous.nine_slice, component.bbox),
          }
        : component;
    });
    setComponents(mergedComponents);
    setSelectedComponents(new Set(mergedComponents.filter((component) => component.selected).map((component) => component.id)));
    if (nextImageSize) {
      setImageSize(nextImageSize);
    }
    if (nextCutoutAssetId) {
      setCutoutAssetId(nextCutoutAssetId);
    }
    if (nextCutoutUrl) {
      setCutoutUrl(nextCutoutUrl);
    }
  }

  function toggleComponent(id: number) {
    setSelectedComponents((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      setComponents((items) => items.map((item) => (item.id === id ? { ...item, selected: next.has(id) } : item)));
      return next;
    });
  }

  function changeComponentBbox(id: number, bbox: [number, number, number, number]) {
    setComponents((items) => items.map((item) => (
      item.id === id
        ? { ...item, bbox, nine_slice: normalizeNineSlice(item.nine_slice, bbox) }
        : item
    )));
  }

  function updateComponent(id: number, patch: Partial<ComponentCandidate>) {
    setComponents((items) => items.map((item) => (
      item.id === id ? { ...item, ...patch } : item
    )));
  }

  function toggleNineSlice(id: number, enabled: boolean) {
    updateComponent(id, { nine_slice: enabled ? [1, 1, 1, 1] : null });
  }

  function changeNineSlice(
    component: ComponentCandidate,
    index: number,
    value: number,
  ) {
    const current = component.nine_slice ?? [1, 1, 1, 1];
    const next = [...current] as [number, number, number, number];
    next[index] = Math.max(0, Math.floor(value));
    updateComponent(component.id, {
      nine_slice: normalizeNineSlice(next, component.bbox),
    });
  }

  function readRegionParameters() {
    return {
      alpha_threshold: params.alpha_threshold,
      min_component_area: params.min_component_area,
    };
  }

  return (
    <>
      <ToolWorkspaceLayout activeToolId="asset-board">
        <section className="preview-stage">
          <WorkbenchPreview key={`asset-board-${asset?.id ?? "empty"}-${cutoutAssetId || "source"}`}>
            {!asset ? (
              <EmptyCanvas />
            ) : (
              <AssetBoardPreview
                imageUrl={asset.url}
                resultUrl={cutoutUrl}
                components={components}
                imageSize={imageSize}
                compare={compare}
                exportPadding={params.export_padding}
                alphaContract={params.alpha_contract}
                alphaFeather={params.alpha_feather}
                alphaDefringe={params.alpha_defringe}
                alphaThreshold={params.alpha_threshold}
                selectedComponents={selectedComponents}
                canWrite={canWrite}
                onCompare={setCompare}
                onToggle={toggleComponent}
                onChangeComponentBbox={changeComponentBbox}
                onManualEdit={openManualEdit}
              />
            )}
          </WorkbenchPreview>
        </section>

        <aside className="settings-panel">
          <h2>{tWorkbench("parameters")}</h2>
          <NumberField label={t("assetBoard.alphaThreshold")} value={params.alpha_threshold} min={0} max={255} onChange={(alpha_threshold) => setParams((current) => ({ ...current, alpha_threshold }))} />
          <NumberField label={t("assetBoard.minimumArea")} value={params.min_component_area} min={1} max={100000} onChange={(min_component_area) => setParams((current) => ({ ...current, min_component_area }))} />
          <NumberField label={t("assetBoard.alphaSmoothing")} value={params.alpha_smoothing} min={0} max={10} onChange={(alpha_smoothing) => setParams((current) => ({ ...current, alpha_smoothing }))} />
          <NumberField label={t("assetBoard.alphaContract")} value={params.alpha_contract} min={0} max={8} onChange={(alpha_contract) => setParams((current) => ({ ...current, alpha_contract }))} />
          <NumberField label={t("assetBoard.alphaFeather")} value={params.alpha_feather} min={0} max={6} onChange={(alpha_feather) => setParams((current) => ({ ...current, alpha_feather }))} />
          <NumberField label={t("assetBoard.alphaDefringe")} value={params.alpha_defringe} min={0} max={8} onChange={(alpha_defringe) => setParams((current) => ({ ...current, alpha_defringe }))} />
          <NumberField label={t("assetBoard.exportPadding")} value={params.export_padding} min={0} max={200} onChange={(export_padding) => setParams((current) => ({ ...current, export_padding }))} />
          {selectedCount ? (
            <section className="ui-component-settings">
              <h3>{t("assetBoard.componentList")}</h3>
              {components.filter((component) => selectedComponents.has(component.id)).map((component) => (
                <article className="ui-component-editor" key={component.id}>
                  <header><strong>{t("assetBoard.component", { id: component.id })}</strong><span>{component.bbox[2]} × {component.bbox[3]}</span></header>
                  <label>{t("assetBoard.componentName")}<input disabled={busy || !canWrite} maxLength={64} value={component.name ?? ""} onChange={(event) => updateComponent(component.id, { name: event.target.value })} /></label>
                  <label>{t("assetBoard.componentState")}<select disabled={busy || !canWrite} value={component.state ?? "normal"} onChange={(event) => updateComponent(component.id, { state: event.target.value as ComponentCandidate["state"] })}>
                    <option value="normal">{t("assetBoard.componentStates.normal")}</option>
                    <option value="hover">{t("assetBoard.componentStates.hover")}</option>
                    <option value="pressed">{t("assetBoard.componentStates.pressed")}</option>
                    <option value="disabled">{t("assetBoard.componentStates.disabled")}</option>
                    <option value="selected">{t("assetBoard.componentStates.selected")}</option>
                  </select></label>
                  <label className="ui-nine-slice-toggle"><input checked={Boolean(component.nine_slice)} disabled={busy || !canWrite} type="checkbox" onChange={(event) => toggleNineSlice(component.id, event.target.checked)} />{t("assetBoard.nineSlice")}</label>
                  {component.nine_slice ? (
                    <div className="ui-nine-slice-grid">
                      {(["left", "top", "right", "bottom"] as const).map((side, index) => (
                        <label key={side}>{t(`assetBoard.sliceSides.${side}`)}<input disabled={busy || !canWrite} min={0} type="number" value={component.nine_slice?.[index] ?? 0} onChange={(event) => changeNineSlice(component, index, Number(event.target.value))} /></label>
                      ))}
                    </div>
                  ) : null}
                </article>
              ))}
            </section>
          ) : null}
          <StatusLine error={error} job={job} />
        </aside>

        <WorkbenchActionBar>
          <ImageUploadAction label={asset ? t("common.replaceImage") : t("common.uploadImage")} disabled={!canWrite} onFile={upload} />
          <button className="primary" disabled={!asset || busy || !canWrite} onClick={() => void detectRegions()} type="button">
            <RefreshCw size={17} strokeWidth={2.4} />
            {t("assetBoard.detect")}
          </button>
          <button className="ghost" disabled={!asset || busy || !canWrite} onClick={() => void cutout()} type="button">
            <Play size={17} strokeWidth={2.4} />
            {t("assetBoard.cutout")}
          </button>
          <button className="ghost" disabled={!cutoutAssetId || busy || !canWrite} onClick={() => void refine()} type="button">
            {t("assetBoard.refreshRegions")}
          </button>
          <button className="ghost" disabled={!cutoutAssetId || busy || selectedCount === 0 || !canWrite} onClick={() => void exportSelected()} type="button">
            {t("assetBoard.exportSelected", { count: selectedCount })}
          </button>
          <button
            className="ghost"
            disabled={!exportAsset}
            type="button"
            onClick={() => (exportAsset ? void downloadOutputAsset(exportAsset, `${asset?.filename ?? "asset-board"}_components.zip`) : undefined)}
          >
            {t("assetBoard.downloadZip")}
          </button>
        </WorkbenchActionBar>
      </ToolWorkspaceLayout>

      <WorkflowFailureDialog failureDialog={failureDialog} onCloseFailure={() => setFailureDialog(null)} />
    </>
  );
}

function readComponents(value: unknown): ComponentCandidate[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item, index) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const record = item as Record<string, unknown>;
    const bbox = record.bbox;
    if (!Array.isArray(bbox) || bbox.length !== 4) {
      return [];
    }
    const component: ComponentCandidate = {
      id: Number(record.id ?? index + 1),
      bbox: [Number(bbox[0]), Number(bbox[1]), Number(bbox[2]), Number(bbox[3])],
      area: Number(record.area ?? 0),
      selected: record.selected !== false,
      name: typeof record.name === "string" ? record.name : `component_${String(Number(record.id ?? index + 1)).padStart(3, "0")}`,
      state: readComponentState(record.state),
      nine_slice: readNineSlice(record.nine_slice),
      preview_asset_id: typeof record.preview_asset_id === "string" ? record.preview_asset_id : null,
      preview_url: typeof record.preview_url === "string" ? record.preview_url : undefined,
    };
    return [cloneComponent(component)];
  });
}

function readComponentState(value: unknown): ComponentCandidate["state"] {
  return ["normal", "hover", "pressed", "disabled", "selected"].includes(String(value))
    ? String(value) as ComponentCandidate["state"]
    : "normal";
}

function readNineSlice(value: unknown): ComponentCandidate["nine_slice"] {
  if (!Array.isArray(value) || value.length !== 4) return null;
  return value.map((item) => Math.max(0, Math.floor(Number(item) || 0))) as [number, number, number, number];
}

function normalizeNineSlice(
  value: ComponentCandidate["nine_slice"],
  bbox: [number, number, number, number],
): ComponentCandidate["nine_slice"] {
  if (!value) return null;
  const width = Math.max(1, Math.floor(bbox[2]));
  const height = Math.max(1, Math.floor(bbox[3]));
  const next = [...value] as [number, number, number, number];
  next[0] = Math.min(Math.max(0, next[0]), Math.max(0, width - next[2] - 1));
  next[2] = Math.min(Math.max(0, next[2]), Math.max(0, width - next[0] - 1));
  next[1] = Math.min(Math.max(0, next[1]), Math.max(0, height - next[3] - 1));
  next[3] = Math.min(Math.max(0, next[3]), Math.max(0, height - next[1] - 1));
  return next;
}

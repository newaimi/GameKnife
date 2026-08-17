import { useEffect, useRef, useState } from "react";
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
import { useWorkflowJob } from "../../hooks/useWorkflowJob";
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

export function AssetBoardWorkspace() {
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
    // 素材板的区域识别是轻量 CPU 步骤，原工程在上传和区域参数变化后会自动刷新框。
    // 这里只监听阈值和最小面积，避免用户微调抠图边缘时隐式创建模型任务。
    await runJob(() => gameKnifeApiClient.createAssetBoardRegionJob(asset.id, readRegionParameters()), applyComponentJobResult);
  }

  async function cutout() {
    if (!asset || !canWrite) {
      return;
    }
    if (!(await ensureModelReady("birefnet"))) {
      return;
    }
    await runJob(async () => {
      const created = await gameKnifeApiClient.createAssetBoardCutoutJob(asset.id, params);
      return created;
    }, applyCutoutJobResult);
  }

  async function refine() {
    if (!canWrite) {
      return;
    }
    if (!cutoutAssetId) {
      setError("请先完成素材板抠图。");
      return;
    }
    await runJob(() => gameKnifeApiClient.createAssetBoardRefineJob(cutoutAssetId, readRegionParameters()), applyComponentJobResult);
  }

  async function exportSelected() {
    if (!canWrite) {
      return;
    }
    if (!cutoutAssetId) {
      setError("请先完成素材板抠图。");
      return;
    }
    await runJob(() =>
      gameKnifeApiClient.createAssetBoardExportJob({
        cutoutAssetId,
        selectedComponentIds: Array.from(selectedComponents),
        components,
        parameters: params,
      }),
    );
  }

  async function runJob(createJob: () => Promise<JobResponse>, onSuccess?: (finished: JobResponse) => void) {
    await runWorkflowJob({
      createJob,
      failureTitle: "任务创建失败",
      failureMessage: "后端拒绝创建素材板任务，下面是接口返回的错误内容。",
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
    setComponents(nextComponents);
    setSelectedComponents(new Set(nextComponents.filter((component) => component.selected).map((component) => component.id)));
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
    setComponents((items) => items.map((item) => (item.id === id ? { ...item, bbox } : item)));
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
          <h2>当前参数</h2>
          <NumberField label="Alpha 阈值" value={params.alpha_threshold} min={0} max={255} onChange={(alpha_threshold) => setParams((current) => ({ ...current, alpha_threshold }))} />
          <NumberField label="最小组件面积" value={params.min_component_area} min={1} max={100000} onChange={(min_component_area) => setParams((current) => ({ ...current, min_component_area }))} />
          <NumberField label="Alpha 平滑" value={params.alpha_smoothing} min={0} max={10} onChange={(alpha_smoothing) => setParams((current) => ({ ...current, alpha_smoothing }))} />
          <NumberField label="边缘内缩" value={params.alpha_contract} min={0} max={8} onChange={(alpha_contract) => setParams((current) => ({ ...current, alpha_contract }))} />
          <NumberField label="边缘柔化" value={params.alpha_feather} min={0} max={6} onChange={(alpha_feather) => setParams((current) => ({ ...current, alpha_feather }))} />
          <NumberField label="去边色" value={params.alpha_defringe} min={0} max={8} onChange={(alpha_defringe) => setParams((current) => ({ ...current, alpha_defringe }))} />
          <NumberField label="导出留边" value={params.export_padding} min={0} max={200} onChange={(export_padding) => setParams((current) => ({ ...current, export_padding }))} />
          <StatusLine error={error} job={job} />
        </aside>

        <WorkbenchActionBar>
          <ImageUploadAction label={asset ? "更换图片" : "上传图片"} disabled={!canWrite} onFile={upload} />
          <button className="primary" disabled={!asset || busy || !canWrite} onClick={() => void detectRegions()} type="button">
            <RefreshCw size={17} strokeWidth={2.4} />
            识别区域
          </button>
          <button className="ghost" disabled={!asset || busy || !canWrite} onClick={() => void cutout()} type="button">
            <Play size={17} strokeWidth={2.4} />
            抠图
          </button>
          <button className="ghost" disabled={!cutoutAssetId || busy || !canWrite} onClick={() => void refine()} type="button">
            刷新框
          </button>
          <button className="ghost" disabled={!cutoutAssetId || busy || selectedCount === 0 || !canWrite} onClick={() => void exportSelected()} type="button">
            导出选中 {selectedCount}
          </button>
          <button
            className="ghost"
            disabled={!exportAsset}
            type="button"
            onClick={() => (exportAsset ? void downloadOutputAsset(exportAsset, `${asset?.filename ?? "asset-board"}_components.zip`) : undefined)}
          >
            下载 ZIP
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
      preview_asset_id: typeof record.preview_asset_id === "string" ? record.preview_asset_id : null,
      preview_url: typeof record.preview_url === "string" ? record.preview_url : undefined,
    };
    return [cloneComponent(component)];
  });
}

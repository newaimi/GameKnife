import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { ComponentCandidate } from "@gameknife/shared-types";
import type { ManualEditSource } from "../types/manualEdit";
import { refineImageDataEdges } from "../utils/alphaMask";
import { clamp } from "../utils/math";
import { useObjectUrl } from "../utils/objectUrl";
import { CompareDragHandle, ResultImage, useContainedImageBox } from "./ImageComparePreview";
import { buildEditedBbox, readImagePointer, type ComponentEditMode, type ComponentEditState } from "./bboxEditing";

export function AssetBoardPreview({
  imageUrl,
  resultUrl,
  components,
  imageSize,
  compare,
  exportPadding,
  alphaContract,
  alphaFeather,
  alphaDefringe,
  alphaThreshold,
  selectedComponents,
  onCompare,
  onToggle,
  onChangeComponentBbox,
  onManualEdit,
}: {
  imageUrl: string;
  resultUrl: string;
  components: ComponentCandidate[];
  imageSize?: [number, number];
  compare: number;
  exportPadding: number;
  alphaContract: number;
  alphaFeather: number;
  alphaDefringe: number;
  alphaThreshold: number;
  selectedComponents: Set<number>;
  onCompare: (value: number) => void;
  onToggle: (id: number) => void;
  onChangeComponentBbox: (id: number, bbox: [number, number, number, number]) => void;
  onManualEdit: (source: Pick<ManualEditSource, "name" | "url" | "sourceFileId" | "sourceContext">) => void | Promise<void>;
}) {
  const resolvedImageUrl = useObjectUrl(imageUrl);
  const resolvedResultUrl = useObjectUrl(resultUrl);
  const previewResultUrl = useEdgeRefinePreviewUrl(resolvedResultUrl, alphaContract, alphaFeather, alphaDefringe, alphaThreshold);
  const previewRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const [activeEdit, setActiveEdit] = useState<ComponentEditState | null>(null);
  const [previewComponent, setPreviewComponent] = useState<ComponentCandidate | null>(null);
  const imageBox = useContainedImageBox(previewRef, resolvedImageUrl);
  const boxes = useMemo(() => {
    if (!imageSize) return [];
    const [width, height] = imageSize;
    return components.map((component) => ({
      ...component,
      left: `${(component.bbox[0] / width) * 100}%`,
      top: `${(component.bbox[1] / height) * 100}%`,
      width: `${(component.bbox[2] / width) * 100}%`,
      height: `${(component.bbox[3] / height) * 100}%`,
    }));
  }, [components, imageSize]);

  useEffect(() => {
    if (!activeEdit || !imageSize) return;

    const handlePointerMove = (event: PointerEvent) => {
      const frame = frameRef.current;
      if (!frame) return;

      event.preventDefault();
      const pointer = readImagePointer(event, frame, imageSize);
      const nextBbox = buildEditedBbox(activeEdit, pointer, imageSize);
      onChangeComponentBbox(activeEdit.componentId, nextBbox);

      const moved =
        activeEdit.moved ||
        Math.abs(pointer.x - activeEdit.startPointer.x) > 1 ||
        Math.abs(pointer.y - activeEdit.startPointer.y) > 1;
      if (moved !== activeEdit.moved) {
        setActiveEdit({ ...activeEdit, moved });
      }
    };

    const handlePointerUp = () => {
      if (activeEdit.mode === "move" && !activeEdit.moved) {
        onToggle(activeEdit.componentId);
      }
      setActiveEdit(null);
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp, { once: true });
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [activeEdit, imageSize, onChangeComponentBbox, onToggle]);

  const startEdit = (event: React.PointerEvent, component: ComponentCandidate, mode: ComponentEditMode) => {
    const frame = frameRef.current;
    if (!frame || !imageSize) return;

    event.preventDefault();
    event.stopPropagation();
    // 拖拽时记录起点，后续只根据这一份起点计算 bbox。
    // 这样可以避免 React 状态连续更新后，下一帧又拿最新 bbox 当起点导致框体漂移。
    setActiveEdit({
      componentId: component.id,
      mode,
      startBbox: component.bbox,
      startPointer: readImagePointer(event.nativeEvent, frame, imageSize),
      moved: mode !== "move",
    });
  };

  return (
    <div className="asset-preview" ref={previewRef}>
      {resolvedImageUrl ? (
        <div className={`asset-frame ${imageBox ? "measured" : ""}`} ref={frameRef} style={imageBox ?? undefined}>
          <img
            className="asset-image"
            src={resolvedImageUrl}
            alt="素材板原图"
            style={previewResultUrl ? { clipPath: `inset(0 ${100 - compare}% 0 0)` } : undefined}
          />
          {previewResultUrl ? (
            <div className="result-layer" style={{ clipPath: `inset(0 0 0 ${compare}%)` }}>
              <ResultImage src={previewResultUrl} alt="素材板抠图预览" />
            </div>
          ) : null}
          {imageBox
            ? boxes.map((component) => (
                <div
                  key={component.id}
                  role="button"
                  tabIndex={0}
                  className={`component-box no-pan ${selectedComponents.has(component.id) ? "selected" : "excluded"} ${
                    activeEdit?.componentId === component.id ? "editing" : ""
                  }`}
                  style={{ left: component.left, top: component.top, width: component.width, height: component.height }}
                  onPointerDown={(event) => startEdit(event, component, "move")}
                  onDoubleClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    if (previewResultUrl) setPreviewComponent(component);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onToggle(component.id);
                    }
                  }}
                  title={`组件 #${component.id}`}
                >
                  #{component.id}
                  <span className="resize-handle nw" onPointerDown={(event) => startEdit(event, component, "nw")} />
                  <span className="resize-handle ne" onPointerDown={(event) => startEdit(event, component, "ne")} />
                  <span className="resize-handle sw" onPointerDown={(event) => startEdit(event, component, "sw")} />
                  <span className="resize-handle se" onPointerDown={(event) => startEdit(event, component, "se")} />
                </div>
              ))
            : null}
          {previewResultUrl ? (
            <>
              <div className="split-line" style={{ left: `${compare}%` }} />
              <CompareDragHandle value={compare} frameRef={frameRef} onChange={onCompare} />
            </>
          ) : null}
          {!components.length ? <span className="canvas-note">正在识别素材...</span> : null}
        </div>
      ) : (
        <span className="canvas-note">正在加载素材板...</span>
      )}
      {previewComponent && previewResultUrl ? (
        <ComponentPreviewModal
          imageUrl={previewResultUrl}
          component={previewComponent}
          exportPadding={exportPadding}
          onManualEdit={onManualEdit}
          onClose={() => setPreviewComponent(null)}
        />
      ) : null}
    </div>
  );
}

function ComponentPreviewModal({
  imageUrl,
  component,
  exportPadding,
  onManualEdit,
  onClose,
}: {
  imageUrl: string;
  component: ComponentCandidate;
  exportPadding: number;
  onManualEdit: (source: Pick<ManualEditSource, "name" | "url" | "sourceFileId" | "sourceContext">) => void | Promise<void>;
  onClose: () => void;
}) {
  const previewUrl = useComponentPreviewUrl(imageUrl, component, exportPadding);
  const [x, y, width, height] = component.bbox;

  const modal = (
    <div className="component-preview-backdrop no-pan" role="presentation" onClick={onClose}>
      <section className="component-preview-modal" role="dialog" aria-modal="true" aria-label={`组件 #${component.id} 预览`} onClick={(event) => event.stopPropagation()}>
        <div className="component-preview-title">
          <div>
            <strong>组件 #{component.id}</strong>
            <span>
              当前框选 {width}×{height}，位置 {x} / {y}
            </span>
          </div>
          <div className="component-preview-actions">
            <button
              className="primary compact"
              type="button"
              disabled={!previewUrl}
              onClick={() => previewUrl && void onManualEdit({ name: `组件-${component.id}.png`, url: previewUrl, sourceContext: "asset_component" })}
            >
              手动编辑
            </button>
            <button className="ghost compact" type="button" onClick={onClose}>
              关闭
            </button>
          </div>
        </div>
        <div className="component-preview-canvas">
          {previewUrl ? <img src={previewUrl} alt={`组件 #${component.id} 裁切预览`} /> : <span>正在生成预览...</span>}
        </div>
        <p className="component-preview-tip">预览会带上当前导出留边，确认边缘没问题后再导出 zip。</p>
      </section>
    </div>
  );

  // 预览区支持缩放和平移，内部会挂 transform。
  // 弹窗放到 body，可以避免 fixed 定位跟着画布一起缩放。
  return createPortal(modal, document.body);
}

function useComponentPreviewUrl(imageUrl: string, component: ComponentCandidate, exportPadding: number) {
  const [previewUrl, setPreviewUrl] = useState("");
  const [x, y, width, height] = component.bbox;

  useEffect(() => {
    setPreviewUrl("");
    if (!imageUrl || width <= 0 || height <= 0) return;

    let cancelled = false;
    const image = new Image();
    image.onload = () => {
      if (cancelled) return;

      const left = clamp(x - exportPadding, 0, image.naturalWidth);
      const top = clamp(y - exportPadding, 0, image.naturalHeight);
      const right = clamp(x + width + exportPadding, left, image.naturalWidth);
      const bottom = clamp(y + height + exportPadding, top, image.naturalHeight);
      const cropWidth = Math.max(1, right - left);
      const cropHeight = Math.max(1, bottom - top);
      const canvas = document.createElement("canvas");
      canvas.width = cropWidth;
      canvas.height = cropHeight;

      const context = canvas.getContext("2d");
      if (!context) return;
      context.clearRect(0, 0, cropWidth, cropHeight);
      context.drawImage(image, left, top, cropWidth, cropHeight, 0, 0, cropWidth, cropHeight);
      setPreviewUrl(canvas.toDataURL("image/png"));
    };
    image.src = imageUrl;

    return () => {
      cancelled = true;
    };
  }, [imageUrl, x, y, width, height, exportPadding]);

  return previewUrl;
}

function useEdgeRefinePreviewUrl(imageUrl: string, alphaContract: number, alphaFeather: number, alphaDefringe: number, alphaThreshold: number) {
  const [previewUrl, setPreviewUrl] = useState(imageUrl);

  useEffect(() => {
    setPreviewUrl(imageUrl);
    const contract = Math.max(0, Number(alphaContract) || 0);
    const feather = Math.max(0, Number(alphaFeather) || 0);
    const defringe = Math.max(0, Math.round(alphaDefringe));
    if (!imageUrl || (contract <= 0 && feather <= 0 && defringe <= 0)) return;

    let cancelled = false;
    let nextObjectUrl = "";
    const image = new Image();
    image.onload = () => {
      if (cancelled) return;

      // 边缘处理是纯前端预览，不写回服务端原始 cutout。
      // 用户调小数值时可以立即恢复细节，最终导出再由后端按同一组参数处理。
      const canvas = document.createElement("canvas");
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      const context = canvas.getContext("2d", { willReadFrequently: true });
      if (!context) return;

      context.clearRect(0, 0, canvas.width, canvas.height);
      context.drawImage(image, 0, 0);
      const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
      refineImageDataEdges(imageData, { contract, feather, defringe, threshold: alphaThreshold });
      context.putImageData(imageData, 0, 0);
      canvas.toBlob((blob) => {
        if (!blob || cancelled) return;
        nextObjectUrl = URL.createObjectURL(blob);
        setPreviewUrl(nextObjectUrl);
      }, "image/png");
    };
    image.src = imageUrl;

    return () => {
      cancelled = true;
      if (nextObjectUrl) URL.revokeObjectURL(nextObjectUrl);
    };
  }, [imageUrl, alphaContract, alphaFeather, alphaDefringe, alphaThreshold]);

  return previewUrl;
}

export function cloneComponent(component: ComponentCandidate): ComponentCandidate {
  return {
    ...component,
    bbox: [...component.bbox] as [number, number, number, number],
  };
}

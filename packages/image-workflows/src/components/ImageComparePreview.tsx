import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { ManualEditSource } from "../types/manualEdit";
import { clamp } from "../utils/math";
import { useObjectUrl } from "../utils/objectUrl";

const PREVIEW_FIT_PADDING = 48;

export function EmptyCanvas() {
  return <div className="empty-canvas" aria-label="空预览区" />;
}

export function ComparePreview({
  original,
  result,
  compare,
  previewTitle = "去背景结果",
  previewDescription = "双击打开的处理后图片。",
  manualEditName = "去背景结果.png",
  manualEditContext = "background_remove",
  manualEditDisabled = false,
  onCompare,
  onManualEdit,
}: {
  original: string;
  result: string;
  compare: number;
  previewTitle?: string;
  previewDescription?: string;
  manualEditName?: string;
  manualEditContext?: string;
  manualEditDisabled?: boolean;
  onCompare: (value: number) => void;
  onManualEdit: (source: Pick<ManualEditSource, "name" | "url" | "sourceFileId" | "sourceContext">) => void | Promise<void>;
}) {
  const originalUrl = useObjectUrl(original);
  const resultUrl = useObjectUrl(result);
  const [previewOpen, setPreviewOpen] = useState(false);
  const previewRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const imageBox = useContainedImageBox(previewRef, originalUrl);

  return (
    <div className="compare-preview" ref={previewRef}>
      {originalUrl ? (
        <div
          className={`compare-frame ${imageBox ? "measured" : ""}`}
          ref={frameRef}
          style={imageBox ?? undefined}
          onDoubleClick={() => {
            if (resultUrl) setPreviewOpen(true);
          }}
        >
          <img
            className="compare-image"
            src={originalUrl}
            alt="原图"
            style={resultUrl ? { clipPath: `inset(0 ${100 - compare}% 0 0)` } : undefined}
          />
          {resultUrl ? (
            <div className="result-layer" style={{ clipPath: `inset(0 0 0 ${compare}%)` }}>
              <ResultImage src={resultUrl} alt="处理后" />
            </div>
          ) : null}
          {resultUrl ? (
            <>
              <div className="split-line" style={{ left: `${compare}%` }} />
              <CompareDragHandle value={compare} frameRef={frameRef} onChange={onCompare} />
            </>
          ) : null}
        </div>
      ) : (
        <span className="canvas-note">正在加载原图...</span>
      )}
      {previewOpen && resultUrl ? (
        <ImagePreviewModal
          title={previewTitle}
          imageUrl={resultUrl}
          description={previewDescription}
          manualEditDisabled={manualEditDisabled}
          onManualEdit={() => onManualEdit({ name: manualEditName, url: resultUrl, sourceContext: manualEditContext })}
          onClose={() => setPreviewOpen(false)}
        />
      ) : null}
    </div>
  );
}

export function useContainedImageBox(containerRef: React.RefObject<HTMLElement | null>, imageUrl: string) {
  const [containerSize, setContainerSize] = useState<{ width: number; height: number } | null>(null);
  const [naturalSize, setNaturalSize] = useState<{ width: number; height: number } | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const syncSize = () => {
      // 这里不能用 getBoundingClientRect()。
      // 预览区位于 react-zoom-pan-pinch 的 transform 层内，getBoundingClientRect 会返回缩放后的视觉尺寸；
      // 如果拿这个值再计算图片适屏尺寸，就会出现“缩放改变容器尺寸，容器尺寸又改变缩放内容”的反馈循环。
      const nextSize = { width: container.clientWidth, height: container.clientHeight };
      setContainerSize((current) =>
        current?.width === nextSize.width && current.height === nextSize.height ? current : nextSize,
      );
    };

    syncSize();
    const resizeObserver = new ResizeObserver(syncSize);
    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, [containerRef]);

  useEffect(() => {
    setNaturalSize(null);
    if (!imageUrl) return;

    let cancelled = false;
    const image = new Image();
    image.onload = () => {
      if (cancelled) return;
      setNaturalSize({ width: image.naturalWidth, height: image.naturalHeight });
    };
    image.src = imageUrl;

    return () => {
      cancelled = true;
    };
  }, [imageUrl]);

  return useMemo(() => {
    if (!containerSize || !naturalSize) return null;
    if (!containerSize.width || !containerSize.height || !naturalSize.width || !naturalSize.height) return null;

    // 预览层必须跟图片实际显示区域一致，不能按整块画布计算。
    // 原图用了 contain 缩放后，画布里会有留白；滑动对比和素材框如果铺满画布，
    // 透明棋盘会画到留白上，素材框也会跟原图错位。
    const availableWidth = Math.max(1, containerSize.width - PREVIEW_FIT_PADDING * 2);
    const availableHeight = Math.max(1, containerSize.height - PREVIEW_FIT_PADDING * 2);
    const scale = Math.min(availableWidth / naturalSize.width, availableHeight / naturalSize.height);
    return {
      width: Math.round(naturalSize.width * scale),
      height: Math.round(naturalSize.height * scale),
    };
  }, [containerSize, naturalSize]);
}

export function ResultImage({ src, alt }: { src: string; alt: string }) {
  return <img className="result-image" src={src} alt={alt} />;
}

export function CompareDragHandle({
  value,
  frameRef,
  onChange,
}: {
  value: number;
  frameRef: React.RefObject<HTMLElement | null>;
  onChange: (value: number) => void;
}) {
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    if (!dragging) return;

    const handlePointerMove = (event: PointerEvent) => {
      event.preventDefault();
      updateCompareFromPointer(event, frameRef, onChange);
    };
    const handlePointerUp = () => setDragging(false);

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp, { once: true });
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [dragging, frameRef, onChange]);

  return (
    <button
      className={`split-handle no-pan ${dragging ? "dragging" : ""}`}
      type="button"
      style={{ left: `${value}%` }}
      aria-label="拖动查看处理前后"
      title="拖动查看处理前后"
      onPointerDown={(event) => {
        event.preventDefault();
        event.stopPropagation();
        // 只有圆形手柄负责滑动对比，不能再铺一层透明控件盖住整张图。
        // 素材框也需要拖拽和缩放，整图命中会抢走它的鼠标事件。
        updateCompareFromPointer(event.nativeEvent, frameRef, onChange);
        setDragging(true);
      }}
      onKeyDown={(event) => {
        const step = event.shiftKey ? 10 : 1;
        if (event.key === "ArrowLeft") {
          event.preventDefault();
          onChange(clamp(value - step, 0, 100));
        }
        if (event.key === "ArrowRight") {
          event.preventDefault();
          onChange(clamp(value + step, 0, 100));
        }
        if (event.key === "Home") {
          event.preventDefault();
          onChange(0);
        }
        if (event.key === "End") {
          event.preventDefault();
          onChange(100);
        }
      }}
    >
      ↔
    </button>
  );
}

function updateCompareFromPointer(
  event: PointerEvent | MouseEvent,
  frameRef: React.RefObject<HTMLElement | null>,
  onChange: (value: number) => void,
) {
  const frame = frameRef.current;
  if (!frame) return;

  const rect = frame.getBoundingClientRect();
  if (!rect.width) return;

  onChange(clamp(((event.clientX - rect.left) / rect.width) * 100, 0, 100));
}


function ImagePreviewModal({
  title,
  imageUrl,
  description,
  manualEditDisabled,
  onManualEdit,
  onClose,
}: {
  title: string;
  imageUrl: string;
  description: string;
  manualEditDisabled: boolean;
  onManualEdit: () => void | Promise<void>;
  onClose: () => void;
}) {
  const modal = (
    <div className="component-preview-backdrop no-pan" role="presentation" onClick={onClose}>
      <section className="component-preview-modal" role="dialog" aria-modal="true" aria-label={`${title}预览`} onClick={(event) => event.stopPropagation()}>
        <div className="component-preview-title">
          <div>
            <strong>{title}</strong>
            <span>{description}</span>
          </div>
          <div className="component-preview-actions">
            <button className="primary compact" type="button" disabled={manualEditDisabled} onClick={() => void onManualEdit()}>
              手动编辑
            </button>
            <button className="ghost compact" type="button" onClick={onClose}>
              关闭
            </button>
          </div>
        </div>
        <div className="component-preview-canvas">
          <img src={imageUrl} alt={title} />
        </div>
      </section>
    </div>
  );

  // 预览弹窗不放在画布内部，避免用户当前缩放倍率影响弹窗尺寸。
  return createPortal(modal, document.body);
}

import React, { useEffect, useRef, useState } from "react";
import { TransformComponent, TransformWrapper, useControls } from "react-zoom-pan-pinch";
const ZOOM_MIN_SCALE = 0.01;
const ZOOM_MAX_SCALE = 100;
const ZOOM_BUTTON_STEP = 0.2;
const ZOOM_WHEEL_STEP_RATIO = 0.0012;
const PIXEL_GRID_MIN_CELL_SIZE = 6;

type CanvasTransformState = {
  scale: number;
  positionX: number;
  positionY: number;
};

type PixelGridState = {
  left: number;
  top: number;
  width: number;
  height: number;
  cellWidth: number;
  cellHeight: number;
  showGrid: boolean;
};

export function WorkbenchPreview({
  children,
  toolbarControls,
  pixelInspect = false,
  pixelGridVisible = true,
  contentMode = "fill",
  emptyLabel,
  onScaleChange,
}: {
  children?: React.ReactNode;
  toolbarControls?: React.ReactNode;
  pixelInspect?: boolean;
  pixelGridVisible?: boolean;
  contentMode?: "fill" | "intrinsic";
  emptyLabel?: string;
  /** 向需要按实际显示倍率调整内容细节的工作区同步当前缩放值。 */
  onScaleChange?: (scale: number) => void;
}) {
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const pixelCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const [scale, setScale] = useState(1);
  const [canvasTransform, setCanvasTransform] = useState<CanvasTransformState>({ scale: 1, positionX: 0, positionY: 0 });
  const wheelStep = readWheelStep(scale);
  const canvasGridStyle = readCanvasGridStyle(canvasTransform);
  const canvasClassName = `canvas${pixelInspect ? " pixel-inspect" : ""}${contentMode === "intrinsic" ? " canvas-intrinsic-content" : ""}`;

  useEffect(() => {
    onScaleChange?.(scale);
  }, [onScaleChange, scale]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const overlay = pixelCanvasRef.current;
    if (!pixelInspect || !canvas) {
      if (overlay) clearPixelInspectionCanvas(overlay);
      return;
    }

    // 图片 DOMRect 会在缩放和平移后更新，延后一帧读取能避免网格跟着旧位置闪动。
    const frame = window.requestAnimationFrame(() => {
      drawPixelInspection(canvas, overlay, pixelGridVisible);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [pixelInspect, pixelGridVisible, canvasTransform, children]);

  useEffect(() => {
    if (!pixelInspect) return;
    const handleResize = () => {
      const canvas = canvasRef.current;
      const overlay = pixelCanvasRef.current;
      if (canvas) drawPixelInspection(canvas, overlay, pixelGridVisible);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [pixelInspect, pixelGridVisible]);

  return (
    <div className={canvasClassName} ref={canvasRef} style={canvasGridStyle}>
      <TransformWrapper
        initialScale={1}
        minScale={ZOOM_MIN_SCALE}
        maxScale={ZOOM_MAX_SCALE}
        centerOnInit
        limitToBounds={false}
        doubleClick={{ disabled: true }}
        panning={{ velocityDisabled: true, excluded: ["no-pan"] }}
        // no-pan 只表达“这里有自己的拖拽逻辑，不能拖动画布”。
        // 滚轮缩放不能共用这个排除规则，否则鼠标停在素材框上时会退回页面滚动。
        wheel={{ step: wheelStep }}
        pinch={{ step: 5 }}
        onTransform={(_ref, state) => {
          setScale(state.scale);
          setCanvasTransform({
            scale: state.scale,
            positionX: state.positionX,
            positionY: state.positionY,
          });
        }}
      >
        <TransformComponent wrapperClass="transform-wrapper" contentClass="transform-content">
          {children ?? (emptyLabel ? <p className="empty-preview">{emptyLabel}</p> : null)}
        </TransformComponent>
        {pixelInspect ? <canvas ref={pixelCanvasRef} className="pixel-canvas-overlay" aria-hidden="true" /> : null}
        <ZoomControls scale={scale}>
          {toolbarControls}
        </ZoomControls>
      </TransformWrapper>
    </div>
  );
}

function ZoomControls({
  scale,
  children,
}: {
  scale: number;
  children?: React.ReactNode;
}) {
  const { zoomIn, zoomOut, resetTransform, centerView } = useControls();

  return (
    <div className="zoom-controls no-pan" aria-label="图片缩放控制">
      {children}
      <button onClick={() => zoomOut(ZOOM_BUTTON_STEP)}>-</button>
      <button className="zoom-value" onClick={() => resetTransform(180)}>
        {formatZoomPercent(scale)}
      </button>
      <button onClick={() => zoomIn(ZOOM_BUTTON_STEP)}>+</button>
      <button className="zoom-fit" onClick={() => centerView(1, 180)}>
        适屏
      </button>
    </div>
  );
}

function readWheelStep(scale: number) {
  // 现在缩放范围很大，固定滚轮步进在 1% 附近会太猛，在 10000% 附近又会太慢。
  // 按当前倍率取比例步进，滚轮每一格的体感会更接近“放大一小段”。
  return clamp(scale * ZOOM_WHEEL_STEP_RATIO, 0.00002, 0.08);
}

function readCanvasGridStyle(transform: CanvasTransformState) {
  const minorSize = Math.max(8, 24 * transform.scale);
  const majorSize = Math.max(40, 120 * transform.scale);

  return {
    "--grid-x": `${transform.positionX}px`,
    "--grid-y": `${transform.positionY}px`,
    "--grid-minor-size": `${minorSize}px`,
    "--grid-major-size": `${majorSize}px`,
  } as React.CSSProperties;
}

function drawPixelInspection(canvas: HTMLElement, overlay: HTMLCanvasElement | null, showGridLines: boolean) {
  if (!overlay) return;

  const image = findPixelInspectionImage(canvas);
  const grid = image ? readPixelGridState(canvas, image) : null;
  if (!image || !grid) {
    clearPixelInspectionCanvas(overlay);
    return;
  }

  drawPixelInspectionCanvas(overlay, canvas, image, grid, showGridLines);
}

function readPixelGridState(canvas: HTMLElement, image: HTMLImageElement): PixelGridState | null {
  if (!image || !image.naturalWidth || !image.naturalHeight) return null;

  const canvasRect = canvas.getBoundingClientRect();
  const imageRect = readRenderedImageRect(image);
  if (imageRect.width <= 0 || imageRect.height <= 0) return null;

  const cellWidth = imageRect.width / image.naturalWidth;
  const cellHeight = imageRect.height / image.naturalHeight;
  return {
    left: imageRect.left - canvasRect.left,
    top: imageRect.top - canvasRect.top,
    width: imageRect.width,
    height: imageRect.height,
    cellWidth,
    cellHeight,
    showGrid: Math.min(cellWidth, cellHeight) >= PIXEL_GRID_MIN_CELL_SIZE,
  };
}

function drawPixelInspectionCanvas(overlay: HTMLCanvasElement, canvas: HTMLElement, image: HTMLImageElement, grid: PixelGridState, showGridLines: boolean) {
  const canvasRect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.round(canvasRect.width * dpr));
  const height = Math.max(1, Math.round(canvasRect.height * dpr));

  if (overlay.width !== width || overlay.height !== height) {
    overlay.width = width;
    overlay.height = height;
  }
  overlay.style.width = `${canvasRect.width}px`;
  overlay.style.height = `${canvasRect.height}px`;

  const context = overlay.getContext("2d");
  if (!context) return;

  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  context.clearRect(0, 0, canvasRect.width, canvasRect.height);
  context.imageSmoothingEnabled = false;

  const visibleLeft = clamp(0 - grid.left, 0, grid.width);
  const visibleTop = clamp(0 - grid.top, 0, grid.height);
  const visibleRight = clamp(canvasRect.width - grid.left, 0, grid.width);
  const visibleBottom = clamp(canvasRect.height - grid.top, 0, grid.height);
  if (visibleRight <= visibleLeft || visibleBottom <= visibleTop) return;

  const sourceLeft = clamp(Math.floor(visibleLeft / grid.cellWidth), 0, image.naturalWidth - 1);
  const sourceTop = clamp(Math.floor(visibleTop / grid.cellHeight), 0, image.naturalHeight - 1);
  const sourceRight = clamp(Math.ceil(visibleRight / grid.cellWidth), sourceLeft + 1, image.naturalWidth);
  const sourceBottom = clamp(Math.ceil(visibleBottom / grid.cellHeight), sourceTop + 1, image.naturalHeight);
  const sourceWidth = sourceRight - sourceLeft;
  const sourceHeight = sourceBottom - sourceTop;
  const destLeft = grid.left + sourceLeft * grid.cellWidth;
  const destTop = grid.top + sourceTop * grid.cellHeight;
  const destWidth = sourceWidth * grid.cellWidth;
  const destHeight = sourceHeight * grid.cellHeight;

  if (!grid.showGrid || !showGridLines) {
    context.drawImage(image, sourceLeft, sourceTop, sourceWidth, sourceHeight, destLeft, destTop, destWidth, destHeight);
    return;
  }

  try {
    const sampleCanvas = document.createElement("canvas");
    sampleCanvas.width = sourceWidth;
    sampleCanvas.height = sourceHeight;
    const sampleContext = sampleCanvas.getContext("2d");
    if (!sampleContext) return;
    sampleContext.imageSmoothingEnabled = false;
    sampleContext.drawImage(image, sourceLeft, sourceTop, sourceWidth, sourceHeight, 0, 0, sourceWidth, sourceHeight);
    const pixels = sampleContext.getImageData(0, 0, sourceWidth, sourceHeight).data;

    for (let y = 0; y < sourceHeight; y += 1) {
      const top = snapToDevicePixel(grid.top + (sourceTop + y) * grid.cellHeight, dpr);
      const bottom = snapToDevicePixel(grid.top + (sourceTop + y + 1) * grid.cellHeight, dpr);
      for (let x = 0; x < sourceWidth; x += 1) {
        const index = (y * sourceWidth + x) * 4;
        const alpha = pixels[index + 3] / 255;
        if (alpha <= 0) continue;
        const left = snapToDevicePixel(grid.left + (sourceLeft + x) * grid.cellWidth, dpr);
        const right = snapToDevicePixel(grid.left + (sourceLeft + x + 1) * grid.cellWidth, dpr);
        context.fillStyle = `rgba(${pixels[index]}, ${pixels[index + 1]}, ${pixels[index + 2]}, ${alpha})`;
        context.fillRect(left, top, right - left, bottom - top);
      }
    }
  } catch {
    context.drawImage(image, sourceLeft, sourceTop, sourceWidth, sourceHeight, destLeft, destTop, destWidth, destHeight);
  }

  drawPixelGridLines(context, grid, sourceLeft, sourceTop, sourceRight, sourceBottom, dpr);
}

function drawPixelGridLines(
  context: CanvasRenderingContext2D,
  grid: PixelGridState,
  sourceLeft: number,
  sourceTop: number,
  sourceRight: number,
  sourceBottom: number,
  dpr: number,
) {
  const lineWidth = 1 / dpr;
  const left = snapToDevicePixel(grid.left + sourceLeft * grid.cellWidth, dpr);
  const top = snapToDevicePixel(grid.top + sourceTop * grid.cellHeight, dpr);
  const right = snapToDevicePixel(grid.left + sourceRight * grid.cellWidth, dpr);
  const bottom = snapToDevicePixel(grid.top + sourceBottom * grid.cellHeight, dpr);

  context.fillStyle = "rgba(23, 103, 255, 0.42)";
  for (let x = sourceLeft; x <= sourceRight; x += 1) {
    const lineX = snapToDevicePixel(grid.left + x * grid.cellWidth, dpr);
    context.fillRect(lineX, top, lineWidth, bottom - top);
  }
  for (let y = sourceTop; y <= sourceBottom; y += 1) {
    const lineY = snapToDevicePixel(grid.top + y * grid.cellHeight, dpr);
    context.fillRect(left, lineY, right - left, lineWidth);
  }
}

function clearPixelInspectionCanvas(overlay: HTMLCanvasElement) {
  const context = overlay.getContext("2d");
  if (context) context.clearRect(0, 0, overlay.width, overlay.height);
}

function snapToDevicePixel(value: number, dpr: number) {
  return Math.round(value * dpr) / dpr;
}

function readRenderedImageRect(image: HTMLImageElement) {
  const elementRect = image.getBoundingClientRect();
  const style = window.getComputedStyle(image);
  const objectFit = style.objectFit;

  if (objectFit !== "contain" && objectFit !== "cover" && objectFit !== "scale-down") {
    return elementRect;
  }

  const naturalWidth = image.naturalWidth;
  const naturalHeight = image.naturalHeight;
  if (!naturalWidth || !naturalHeight) return elementRect;

  const fitRatio =
    objectFit === "cover"
      ? Math.max(elementRect.width / naturalWidth, elementRect.height / naturalHeight)
      : Math.min(elementRect.width / naturalWidth, elementRect.height / naturalHeight, objectFit === "scale-down" ? 1 : Infinity);
  const renderedWidth = naturalWidth * fitRatio;
  const renderedHeight = naturalHeight * fitRatio;

  // object-fit: contain 会让真实图片在 img 元素内部留白。像素网格必须对齐真实绘制区域，
  // 否则格子会跟元素外框对齐，看起来就像“像素没有落进格子里”。
  return {
    left: elementRect.left + (elementRect.width - renderedWidth) / 2,
    top: elementRect.top + (elementRect.height - renderedHeight) / 2,
    width: renderedWidth,
    height: renderedHeight,
  };
}

function findPixelInspectionImage(canvas: HTMLElement): HTMLImageElement | null {
  const preferredSelectors = [".active-frame", ".rig-source-image", ".asset-image", ".compare-image", ".result-image"];
  for (const selector of preferredSelectors) {
    const image = canvas.querySelector<HTMLImageElement>(selector);
    if (isInspectableImage(image)) return image;
  }

  const images = Array.from(canvas.querySelectorAll<HTMLImageElement>("img")).filter(isInspectableImage);
  return images.sort((firstImage, secondImage) => {
    const first = firstImage.getBoundingClientRect();
    const second = secondImage.getBoundingClientRect();
    return second.width * second.height - first.width * first.height;
  })[0] ?? null;
}

function isInspectableImage(image: HTMLImageElement | null): image is HTMLImageElement {
  if (!image || !image.naturalWidth || !image.naturalHeight) return false;
  const rect = image.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

function formatZoomPercent(scale: number) {
  const percent = scale * 100;
  if (percent < 10) return `${percent.toFixed(1)}%`;
  return `${Math.round(percent)}%`;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

export interface EditorSize {
  width: number;
  height: number;
}

export interface EditorDocument {
  id: string;
  name: string;
  size: EditorSize;
  sourceAssetId?: string;
}

export type BrushMode = "paint" | "erase";

export interface BrushPoint {
  x: number;
  y: number;
}

export interface BrushOptions {
  mode: BrushMode;
  size: number;
  color: string;
}

export function createManualEditDocument(id: string, name: string, size: EditorSize, sourceAssetId?: string): EditorDocument {
  // 编辑器核心只保存和图像处理相关的最小状态，React 页面负责工具栏和临时交互状态。
  // 这样 Community 和 Studio 复用时不会把路由、权限或账号信息带进编辑核心。
  return {
    id,
    name,
    size,
    sourceAssetId,
  };
}

export async function drawBlobToCanvas(canvas: HTMLCanvasElement, blob: Blob): Promise<EditorSize> {
  const image = await loadImage(blob);
  canvas.width = image.naturalWidth || image.width;
  canvas.height = image.naturalHeight || image.height;
  const context = requireCanvasContext(canvas);
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.imageSmoothingEnabled = false;
  context.drawImage(image, 0, 0);
  return { width: canvas.width, height: canvas.height };
}

export function drawBrushStroke(canvas: HTMLCanvasElement, point: BrushPoint, options: BrushOptions): void {
  const context = requireCanvasContext(canvas);
  const radius = Math.max(1, options.size) / 2;
  context.save();
  context.beginPath();
  context.arc(point.x, point.y, radius, 0, Math.PI * 2);
  if (options.mode === "erase") {
    // 橡皮必须改写 alpha 通道，不能用白色覆盖。
    // 游戏素材后续还会继续抠图、拆帧或导出，透明像素需要作为真实图像数据保存。
    context.globalCompositeOperation = "destination-out";
    context.fillStyle = "rgba(0, 0, 0, 1)";
  } else {
    context.globalCompositeOperation = "source-over";
    context.fillStyle = options.color;
  }
  context.fill();
  context.restore();
}

export async function exportCanvasAsPngBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob) {
        reject(new Error("手动编辑结果无法导出。"));
        return;
      }
      resolve(blob);
    }, "image/png");
  });
}

export function readCanvasPoint(canvas: HTMLCanvasElement, clientX: number, clientY: number): BrushPoint {
  const rect = canvas.getBoundingClientRect();
  const scaleX = canvas.width / Math.max(1, rect.width);
  const scaleY = canvas.height / Math.max(1, rect.height);
  return {
    x: Math.floor((clientX - rect.left) * scaleX),
    y: Math.floor((clientY - rect.top) * scaleY),
  };
}

function requireCanvasContext(canvas: HTMLCanvasElement): CanvasRenderingContext2D {
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) {
    throw new Error("浏览器无法创建 Canvas 画布。");
  }
  return context;
}

function loadImage(blob: Blob): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(blob);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("图片读取失败。"));
    };
    image.src = url;
  });
}

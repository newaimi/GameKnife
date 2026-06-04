import { clamp } from "../utils/math";

export type ComponentEditMode = "move" | "nw" | "ne" | "sw" | "se";

export type ImagePoint = { x: number; y: number };

export type BoxEditState = {
  mode: ComponentEditMode;
  startBbox: [number, number, number, number];
  startPointer: ImagePoint;
};

export type ComponentEditState = BoxEditState & {
  componentId: number;
  moved: boolean;
};

export type RigPartEditState = BoxEditState & {
  partId: string;
  moved: boolean;
};

export function readImagePointer(event: PointerEvent | MouseEvent, frame: HTMLElement, imageSize: [number, number]): ImagePoint {
  const rect = frame.getBoundingClientRect();
  const [imageWidth, imageHeight] = imageSize;
  return {
    x: clamp(((event.clientX - rect.left) / rect.width) * imageWidth, 0, imageWidth),
    y: clamp(((event.clientY - rect.top) / rect.height) * imageHeight, 0, imageHeight),
  };
}

export function buildEditedBbox(edit: BoxEditState, pointer: ImagePoint, imageSize: [number, number]): [number, number, number, number] {
  const [imageWidth, imageHeight] = imageSize;
  const [startX, startY, startWidth, startHeight] = edit.startBbox;
  const dx = pointer.x - edit.startPointer.x;
  const dy = pointer.y - edit.startPointer.y;
  const minSize = 6;
  let left = startX;
  let top = startY;
  let right = startX + startWidth;
  let bottom = startY + startHeight;

  if (edit.mode === "move") {
    left = clamp(startX + dx, 0, imageWidth - startWidth);
    top = clamp(startY + dy, 0, imageHeight - startHeight);
    right = left + startWidth;
    bottom = top + startHeight;
  } else {
    if (edit.mode.includes("w")) left = clamp(startX + dx, 0, right - minSize);
    if (edit.mode.includes("e")) right = clamp(startX + startWidth + dx, left + minSize, imageWidth);
    if (edit.mode.includes("n")) top = clamp(startY + dy, 0, bottom - minSize);
    if (edit.mode.includes("s")) bottom = clamp(startY + startHeight + dy, top + minSize, imageHeight);
  }

  return [Math.round(left), Math.round(top), Math.round(right - left), Math.round(bottom - top)];
}

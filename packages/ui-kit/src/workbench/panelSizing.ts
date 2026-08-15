export type PanelResizeSide = "left" | "right";

export function clampPanelWidth(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

export function calculatePanelWidth({
  side,
  startWidth,
  startPointer,
  currentPointer,
  min,
  max,
}: {
  side: PanelResizeSide;
  startWidth: number;
  startPointer: number;
  currentPointer: number;
  min: number;
  max: number;
}) {
  const pointerDelta = currentPointer - startPointer;
  const widthDelta = side === "left" ? pointerDelta : -pointerDelta;
  return clampPanelWidth(startWidth + widthDelta, min, max);
}

export function calculateKeyboardPanelWidth({
  side,
  width,
  key,
  min,
  max,
  step = 16,
}: {
  side: PanelResizeSide;
  width: number;
  key: string;
  min: number;
  max: number;
  step?: number;
}) {
  if (key === "Home") return min;
  if (key === "End") return max;

  const direction = key === "ArrowLeft" ? -1 : key === "ArrowRight" ? 1 : 0;
  if (direction === 0) return width;
  const widthDirection = side === "left" ? direction : -direction;
  return clampPanelWidth(width + widthDirection * step, min, max);
}

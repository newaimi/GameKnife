import { useRef, type KeyboardEvent, type PointerEvent } from "react";
import { calculateKeyboardPanelWidth, calculatePanelWidth, type PanelResizeSide } from "./panelSizing.js";

export type PanelResizeHandleProps = {
  side: PanelResizeSide;
  value: number;
  min: number;
  max: number;
  label: string;
  disabled?: boolean;
  className?: string;
  onChange: (value: number) => void;
};

type DragState = {
  pointerId: number;
  startPointer: number;
  startWidth: number;
};

/**
 * Supports pointer and keyboard resizing for workbench panels. The parent owns collapse and persistence state,
 * which keeps this interaction reusable without inheriting tool-navigation rules.
 */
export function PanelResizeHandle({ side, value, min, max, label, disabled = false, className, onChange }: PanelResizeHandleProps) {
  const dragRef = useRef<DragState | null>(null);
  const classes = ["gk-panel-resize-handle", className].filter(Boolean).join(" ");

  function handlePointerDown(event: PointerEvent<HTMLDivElement>) {
    if (disabled || event.button !== 0) return;
    dragRef.current = {
      pointerId: event.pointerId,
      startPointer: event.clientX,
      startWidth: value,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function handlePointerMove(event: PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    onChange(
      calculatePanelWidth({
        side,
        startWidth: drag.startWidth,
        startPointer: drag.startPointer,
        currentPointer: event.clientX,
        min,
        max,
      }),
    );
  }

  function finishPointerDrag(event: PointerEvent<HTMLDivElement>) {
    if (dragRef.current?.pointerId !== event.pointerId) return;
    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (disabled || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    onChange(calculateKeyboardPanelWidth({ side, width: value, key: event.key, min, max }));
  }

  return (
    <div
      className={classes}
      role="separator"
      aria-label={label}
      aria-orientation="vertical"
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={Math.round(value)}
      aria-disabled={disabled}
      tabIndex={disabled ? -1 : 0}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={finishPointerDrag}
      onPointerCancel={finishPointerDrag}
      onLostPointerCapture={() => {
        dragRef.current = null;
      }}
      onKeyDown={handleKeyDown}
    />
  );
}

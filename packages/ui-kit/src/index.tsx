import type { ReactNode } from "react";

export interface NumberFieldProps {
  label: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (value: number) => void;
}

export function NumberField({ label, value, min, max, step = 1, onChange }: NumberFieldProps) {
  return (
    <label className="number-field">
      <span>{label}</span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

export interface WorkbenchPreviewProps {
  children?: ReactNode;
  emptyLabel?: string;
}

export function WorkbenchPreview({ children, emptyLabel = "暂无素材" }: WorkbenchPreviewProps) {
  return <section className="workbench-preview">{children ?? <span>{emptyLabel}</span>}</section>;
}

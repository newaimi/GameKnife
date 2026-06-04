import { useEffect, useMemo, useRef, useState } from "react";
import {
  DATE_PICKER_WEEKDAYS,
  buildDatePickerDays,
  formatDatePickerMonth,
  formatDatePickerValue,
  isSameLocalDate,
  parseDateInput,
  toDateInputValue,
} from "./jobHistory";

export function DatePickerField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [visibleMonth, setVisibleMonth] = useState(() => parseDateInput(value) ?? new Date());
  const selectedDate = parseDateInput(value);
  const selectedTime = selectedDate?.getTime();
  const days = useMemo(() => buildDatePickerDays(visibleMonth), [visibleMonth]);

  useEffect(() => {
    if (!open) return;
    // 浏览器原生日历弹层样式不可控，暗色模式下会直接使用系统控件。
    // 自维护可见月份后，任务页在亮暗主题下都能保持和原工程一致的视觉状态。
    setVisibleMonth(selectedDate ?? new Date());
  }, [open, selectedTime]);

  useEffect(() => {
    if (!open) return undefined;

    const handlePointerDown = (event: PointerEvent) => {
      const root = rootRef.current;
      if (!root || root.contains(event.target as Node)) return;
      setOpen(false);
    };

    window.addEventListener("pointerdown", handlePointerDown);
    return () => window.removeEventListener("pointerdown", handlePointerDown);
  }, [open]);

  const moveMonth = (offset: number) => {
    setVisibleMonth((current) => new Date(current.getFullYear(), current.getMonth() + offset, 1));
  };

  const selectDate = (date: Date) => {
    onChange(toDateInputValue(date));
    setOpen(false);
  };

  return (
    <div className="date-picker" ref={rootRef}>
      <span className="date-picker-label">{label}</span>
      <button className={`date-trigger ${open ? "active" : ""}`} type="button" onClick={() => setOpen((current) => !current)}>
        <span>{formatDatePickerValue(value)}</span>
        <strong>日历</strong>
      </button>
      {open ? (
        <div className="date-popover">
          <div className="date-picker-header">
            <button type="button" aria-label="上个月" onClick={() => moveMonth(-1)}>
              ‹
            </button>
            <strong>{formatDatePickerMonth(visibleMonth)}</strong>
            <button type="button" aria-label="下个月" onClick={() => moveMonth(1)}>
              ›
            </button>
          </div>
          <div className="date-weekdays">
            {DATE_PICKER_WEEKDAYS.map((weekday) => (
              <span key={weekday}>{weekday}</span>
            ))}
          </div>
          <div className="date-grid">
            {days.map((item) => (
              <button
                key={item.key}
                className={["date-day", item.inCurrentMonth ? "" : "outside", item.value === value ? "selected" : "", isSameLocalDate(item.date, new Date()) ? "today" : ""]
                  .filter(Boolean)
                  .join(" ")}
                type="button"
                onClick={() => selectDate(item.date)}
              >
                {item.date.getDate()}
              </button>
            ))}
          </div>
          <div className="date-picker-footer">
            <button
              type="button"
              onClick={() => {
                onChange("");
                setOpen(false);
              }}
            >
              清空
            </button>
            <button type="button" onClick={() => selectDate(new Date())}>
              今天
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

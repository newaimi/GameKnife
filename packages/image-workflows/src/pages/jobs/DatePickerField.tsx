import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  buildDatePickerDays,
  formatDatePickerMonth,
  formatDatePickerValue,
  isSameLocalDate,
  parseDateInput,
  toDateInputValue,
} from "./jobHistory";

export function DatePickerField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  const { i18n, t } = useTranslation("jobs");
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [visibleMonth, setVisibleMonth] = useState(() => parseDateInput(value) ?? new Date());
  const selectedDate = parseDateInput(value);
  const selectedTime = selectedDate?.getTime();
  const days = useMemo(() => buildDatePickerDays(visibleMonth), [visibleMonth]);
  const weekdays = t("calendar.weekdays", { returnObjects: true }) as unknown as string[];

  useEffect(() => {
    if (!open) return;
    // Native calendar popovers cannot be styled consistently across themes.
    // Keeping the visible month here gives both themes the same project-specific UI.
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
        <span>{formatDatePickerValue(value, i18n.resolvedLanguage ?? i18n.language, t("calendar.chooseDate"))}</span>
        <strong>{t("calendar.calendar")}</strong>
      </button>
      {open ? (
        <div className="date-popover">
          <div className="date-picker-header">
            <button type="button" aria-label={t("calendar.previousMonth")} onClick={() => moveMonth(-1)}>
              ‹
            </button>
            <strong>{formatDatePickerMonth(visibleMonth, i18n.resolvedLanguage ?? i18n.language)}</strong>
            <button type="button" aria-label={t("calendar.nextMonth")} onClick={() => moveMonth(1)}>
              ›
            </button>
          </div>
          <div className="date-weekdays">
            {weekdays.map((weekday) => (
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
              {t("calendar.clear")}
            </button>
            <button type="button" onClick={() => selectDate(new Date())}>
              {t("calendar.today")}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

import type { JobResponse, OutputAssetRef } from "@gameknife/shared-types";
import { downloadJobOutputAsset } from "../../utils/assets";

export {
  formatAbsoluteTime,
  formatRelativeTime,
  formatJobFileMeta,
  formatJobStatus,
  readJobDisplayName,
  readJobInitial,
  readJobThumbnailPath,
  readJobTitle,
} from "../../utils/jobPresentation";

export const JOB_LIST_PAGE_SIZE = 12;

export const JOB_CATEGORY_OPTIONS = [
  { value: "all", translationKey: "all" },
  { value: "background", translationKey: "background" },
  { value: "upscale", translationKey: "upscale" },
  { value: "sound", translationKey: "sound" },
  { value: "asset_board", translationKey: "assetBoard" },
  { value: "sequence", translationKey: "sequence" },
];

export async function downloadJobAsset(job: JobResponse, asset: OutputAssetRef) {
  await downloadJobOutputAsset(job, asset);
}

export function dateInputToStartIso(value: string) {
  if (!value) return undefined;
  return new Date(`${value}T00:00:00`).toISOString();
}

export function dateInputToEndIso(value: string) {
  if (!value) return undefined;
  const date = new Date(`${value}T00:00:00`);
  date.setDate(date.getDate() + 1);
  date.setMilliseconds(date.getMilliseconds() - 1);
  return date.toISOString();
}

export function parseDateInput(value: string) {
  if (!value) return null;
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return null;
  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) return null;
  return date;
}

export function toDateInputValue(date: Date) {
  return `${date.getFullYear()}-${padDateNumber(date.getMonth() + 1)}-${padDateNumber(date.getDate())}`;
}

export function formatDatePickerValue(value: string, language: string, emptyLabel: string) {
  const date = parseDateInput(value);
  if (!date) return emptyLabel;
  return new Intl.DateTimeFormat(language, { year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
}

export function formatDatePickerMonth(date: Date, language: string) {
  return new Intl.DateTimeFormat(language, { year: "numeric", month: "long" }).format(date);
}

export function buildDatePickerDays(monthDate: Date) {
  const firstDay = new Date(monthDate.getFullYear(), monthDate.getMonth(), 1);
  const mondayOffset = (firstDay.getDay() + 6) % 7;
  const startDate = new Date(firstDay);
  startDate.setDate(firstDay.getDate() - mondayOffset);

  return Array.from({ length: 42 }, (_, index) => {
    const date = new Date(startDate);
    date.setDate(startDate.getDate() + index);
    return {
      key: toDateInputValue(date),
      date,
      value: toDateInputValue(date),
      inCurrentMonth: date.getMonth() === monthDate.getMonth(),
    };
  });
}

export function isSameLocalDate(first: Date, second: Date) {
  return first.getFullYear() === second.getFullYear() && first.getMonth() === second.getMonth() && first.getDate() === second.getDate();
}

function padDateNumber(value: number) {
  return String(value).padStart(2, "0");
}

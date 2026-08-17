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

export const JOB_CATEGORY_OPTIONS: Array<{ value: string; label: string; note: string }> = [
  { value: "all", label: "全部", note: "所有可下载结果" },
  { value: "background", label: "抠图任务", note: "AI 去背景结果" },
  { value: "upscale", label: "图片放大", note: "超分和像素放大" },
  { value: "sound", label: "声效生成", note: "文字生成 WAV" },
  { value: "asset_board", label: "素材拆分", note: "素材板抠图和导出" },
  { value: "sequence", label: "序列帧", note: "PNG 序列和 Spine 工程" },
];

export const DATE_PICKER_WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];

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

export function formatDatePickerValue(value: string) {
  const date = parseDateInput(value);
  if (!date) return "选择日期";
  return `${date.getFullYear()}年${padDateNumber(date.getMonth() + 1)}月${padDateNumber(date.getDate())}日`;
}

export function formatDatePickerMonth(date: Date) {
  return `${date.getFullYear()}年 ${date.getMonth() + 1}月`;
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

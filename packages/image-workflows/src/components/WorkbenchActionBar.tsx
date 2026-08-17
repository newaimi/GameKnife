import type { ReactNode } from "react";
import { Upload } from "lucide-react";

type FileUploadHandler = (file: File) => void | Promise<unknown>;
type FilesUploadHandler = (files: File[]) => void | Promise<unknown>;

/**
 * 承载当前工具最主要的文件、处理和导出操作。
 *
 * 操作栏由各工作流传入按钮，公共组件只负责固定位置和无障碍语义，
 * 避免布局层根据任务类型推断按钮状态，保持各工作流可以独立运行。
 */
export function WorkbenchActionBar({ children }: { children: ReactNode }) {
  return (
    <div className="workbench-action-bar no-pan" role="toolbar" aria-label="工作台操作">
      {children}
    </div>
  );
}

/**
 * 图片工作流的单文件入口。文件校验继续由既有上传 hook 和后端负责，
 * 这里仅限制浏览器文件选择范围，并把第一个文件交给调用方。
 */
export function ImageUploadAction({
  label,
  disabled = false,
  onFile,
}: {
  label: string;
  disabled?: boolean;
  onFile: FileUploadHandler;
}) {
  return (
    <FileUploadAction
      label={label}
      accept="image/jpeg,image/png,image/webp"
      disabled={disabled}
      onFiles={(files) => {
        const file = files[0];
        return file ? onFile(file) : undefined;
      }}
    />
  );
}

/**
 * 序列帧工作流的多文件入口。文件顺序按浏览器返回顺序原样传递，
 * 由既有导入流程统一推断序列名称和帧顺序。
 */
export function ImageSequenceUploadAction({
  label,
  disabled = false,
  onFiles,
}: {
  label: string;
  disabled?: boolean;
  onFiles: FilesUploadHandler;
}) {
  return <FileUploadAction label={label} accept="image/jpeg,image/png,image/webp" multiple disabled={disabled} onFiles={onFiles} />;
}

/**
 * 视频转帧工作流的单文件入口。扩展名和 MIME 类型同时声明，
 * 用于兼容部分 Windows 浏览器无法从 MOV 文件读取标准 MIME 类型的情况。
 */
export function VideoUploadAction({
  label,
  disabled = false,
  onFile,
}: {
  label: string;
  disabled?: boolean;
  onFile: FileUploadHandler;
}) {
  return (
    <FileUploadAction
      label={label}
      accept="video/mp4,video/webm,video/quicktime,.mp4,.webm,.mov"
      disabled={disabled}
      onFiles={(files) => {
        const file = files[0];
        return file ? onFile(file) : undefined;
      }}
    />
  );
}

/**
 * 把原生文件输入包装成与处理按钮一致的紧凑操作。
 * 每次选择后清空 input，保证用户连续选择同一个文件时仍会触发上传。
 */
function FileUploadAction({
  label,
  accept,
  multiple = false,
  disabled,
  onFiles,
}: {
  label: string;
  accept: string;
  multiple?: boolean;
  disabled: boolean;
  onFiles: FilesUploadHandler;
}) {
  return (
    <label className={`workbench-file-action ghost ${disabled ? "disabled" : ""}`} aria-disabled={disabled}>
      <input
        type="file"
        accept={accept}
        multiple={multiple}
        disabled={disabled}
        onChange={(event) => {
          const files = Array.from(event.currentTarget.files ?? []);
          if (files.length > 0) {
            void onFiles(files);
          }
          event.currentTarget.value = "";
        }}
      />
      <Upload size={17} strokeWidth={2.4} />
      <span>{label}</span>
    </label>
  );
}

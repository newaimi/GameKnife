import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Upload } from "lucide-react";

type FileUploadHandler = (file: File) => void | Promise<unknown>;
type FilesUploadHandler = (files: File[]) => void | Promise<unknown>;

/**
 * Hosts the primary file, processing, and export actions for the active tool.
 * Workflows own their buttons and state so the shared layout never infers workflow behavior.
 */
export function WorkbenchActionBar({ children }: { children: ReactNode }) {
  const { t } = useTranslation("workbench");

  return (
    <div className="workbench-action-bar no-pan" role="toolbar" aria-label={t("actionsLabel")}>
      {children}
    </div>
  );
}

/**
 * Provides the single-image entry point while existing upload hooks and the backend retain file validation ownership.
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
 * Passes selected images in browser order so the existing import flow remains responsible for sequence naming and sorting.
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
 * Declares both extensions and MIME types because some Windows browsers do not report a standard MIME type for MOV files.
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
 * Wraps the native input as a compact action and clears it after each selection so choosing the same file emits another change.
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

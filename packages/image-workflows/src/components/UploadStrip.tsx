import { Upload } from "lucide-react";

type FileUploadHandler = (file: File) => void | Promise<unknown>;
type FilesUploadHandler = (files: File[]) => void | Promise<unknown>;

export function ImageUploadStrip({
  title,
  description,
  actionLabel = "更换图片",
  disabled = false,
  onFile,
}: {
  title: string;
  description: string;
  actionLabel?: string;
  disabled?: boolean;
  onFile: FileUploadHandler;
}) {
  return (
    <label className={`upload-strip ${disabled ? "disabled" : ""}`}>
      <input
        type="file"
        accept="image/jpeg,image/png,image/webp"
        hidden
        disabled={disabled}
        onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          if (file) {
            void onFile(file);
          }
          event.currentTarget.value = "";
        }}
      />
      <div className="upload-icon">
        <Upload size={34} strokeWidth={2.5} />
      </div>
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
      </div>
      <span className="ghost">{actionLabel}</span>
    </label>
  );
}

export function ImageSequenceUploadStrip({
  title,
  description,
  actionLabel = "更换序列",
  disabled = false,
  onFiles,
}: {
  title: string;
  description: string;
  actionLabel?: string;
  disabled?: boolean;
  onFiles: FilesUploadHandler;
}) {
  return (
    <label className={`upload-strip ${disabled ? "disabled" : ""}`}>
      <input
        type="file"
        accept="image/jpeg,image/png,image/webp"
        multiple
        hidden
        disabled={disabled}
        onChange={(event) => {
          const files = Array.from(event.currentTarget.files ?? []);
          if (files.length) {
            void onFiles(files);
          }
          event.currentTarget.value = "";
        }}
      />
      <div className="upload-icon">
        <Upload size={34} strokeWidth={2.5} />
      </div>
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
      </div>
      <span className="ghost">{actionLabel}</span>
    </label>
  );
}

export function VideoUploadStrip({
  title,
  description,
  actionLabel = "更换视频",
  disabled = false,
  onFile,
}: {
  title: string;
  description: string;
  actionLabel?: string;
  disabled?: boolean;
  onFile: FileUploadHandler;
}) {
  return (
    <label className={`upload-strip ${disabled ? "disabled" : ""}`}>
      <input
        type="file"
        accept="video/mp4,video/webm,video/quicktime,.mp4,.webm,.mov"
        hidden
        disabled={disabled}
        onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          if (file) {
            void onFile(file);
          }
          event.currentTarget.value = "";
        }}
      />
      <div className="upload-icon">
        <Upload size={34} strokeWidth={2.5} />
      </div>
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
      </div>
      <span className="ghost">{actionLabel}</span>
    </label>
  );
}

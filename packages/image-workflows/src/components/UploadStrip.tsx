import { Upload } from "lucide-react";

type FileUploadHandler = (file: File) => void | Promise<unknown>;
type FilesUploadHandler = (files: File[]) => void | Promise<unknown>;

export function ImageUploadStrip({
  title,
  description,
  actionLabel = "更换图片",
  onFile,
}: {
  title: string;
  description: string;
  actionLabel?: string;
  onFile: FileUploadHandler;
}) {
  return (
    <label className="upload-strip">
      <input
        type="file"
        accept="image/jpeg,image/png,image/webp"
        hidden
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
  onFiles,
}: {
  title: string;
  description: string;
  actionLabel?: string;
  onFiles: FilesUploadHandler;
}) {
  return (
    <label className="upload-strip">
      <input
        type="file"
        accept="image/jpeg,image/png,image/webp"
        multiple
        hidden
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
  onFile,
}: {
  title: string;
  description: string;
  actionLabel?: string;
  onFile: FileUploadHandler;
}) {
  return (
    <label className="upload-strip">
      <input
        type="file"
        accept="video/mp4,video/webm,video/quicktime,.mp4,.webm,.mov"
        hidden
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

import { Download, Trash2 } from "lucide-react";
import type { JobResponse, OutputAssetRef } from "@gameknife/shared-types";
import { useObjectUrl } from "../../utils/objectUrl";
import { readFirstJobOutputAsset } from "../../utils/jobs";
import { formatAbsoluteTime, formatJobFileMeta, formatJobStatus, readJobDisplayName, readJobInitial, readJobThumbnailPath, readJobTitle } from "./jobHistory";

export function JobHistoryRow({
  deletingJobId,
  downloadingAssetId,
  job,
  onDelete,
  onDownload,
}: {
  deletingJobId: string;
  downloadingAssetId: string;
  job: JobResponse;
  onDelete: (job: JobResponse) => void | Promise<void>;
  onDownload: (job: JobResponse, asset: OutputAssetRef) => void | Promise<void>;
}) {
  const thumbnailUrl = useObjectUrl(readJobThumbnailPath(job));
  const outputAsset = readFirstJobOutputAsset(job);
  const isDownloading = outputAsset ? downloadingAssetId === outputAsset.id : false;
  const isDeleting = deletingJobId === job.id;

  return (
    <article className="task-row">
      <div className="recent-thumb task-row-thumb">
        {thumbnailUrl ? <img src={thumbnailUrl} alt={readJobDisplayName(job)} /> : <span>{readJobInitial(job)}</span>}
      </div>
      <div className="task-row-main">
        <div>
          <strong title={readJobDisplayName(job)}>{readJobDisplayName(job)}</strong>
          <span>{readJobTitle(job)}</span>
        </div>
        <p>
          {formatJobFileMeta(job)} · {formatAbsoluteTime(job.updated_at)}
        </p>
      </div>
      <span className="task-status-pill">{formatJobStatus(job.status)}</span>
      <div className="recent-actions">
        <button
          className="recent-icon-button"
          type="button"
          title={outputAsset ? "下载结果" : "当前任务没有可下载文件"}
          disabled={!outputAsset || isDownloading}
          onClick={() => outputAsset && void onDownload(job, outputAsset)}
        >
          <Download size={18} strokeWidth={2.2} />
        </button>
        <button className="recent-icon-button danger" type="button" title="删除任务" disabled={isDeleting} onClick={() => void onDelete(job)}>
          <Trash2 size={18} strokeWidth={2.2} />
        </button>
      </div>
    </article>
  );
}

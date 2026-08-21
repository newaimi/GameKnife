import type { JobResponse, OutputAssetRef } from "@gameknife/shared-types";
import { JobAssetActions } from "../../components/JobAssetActions";
import { RotateCcw } from "lucide-react";
import { IconButton } from "@gameknife/ui-kit";
import type { JobListMetadata } from "./CommunityJobsPage";
import { JobStatusBadge } from "../../components/JobStatusBadge";
import { useObjectUrl } from "../../utils/objectUrl";
import { readFirstJobOutputAsset } from "../../utils/jobs";
import { formatAbsoluteTime, formatJobFileMeta, readJobDisplayName, readJobInitial, readJobThumbnailPath, readJobTitle } from "./jobHistory";

export function JobHistoryRow({
  deletingJobId,
  downloadingAssetId,
  job,
  onDelete,
  onDownload,
  onRetry,
  metadata,
}: {
  deletingJobId: string;
  downloadingAssetId: string;
  job: JobResponse;
  onDelete: (job: JobResponse) => void | Promise<void>;
  onDownload: (job: JobResponse, asset: OutputAssetRef) => void | Promise<void>;
  onRetry: (job: JobResponse) => void;
  metadata?: JobListMetadata;
}) {
  const thumbnailUrl = useObjectUrl(readJobThumbnailPath(job));
  const outputAsset = readFirstJobOutputAsset(job);
  const isDownloading = outputAsset ? downloadingAssetId === outputAsset.id : false;
  const isDeleting = deletingJobId === job.id;

  return (
    <article className="task-row">
      <div className="job-thumb task-row-thumb">
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
        {metadata ? <p className="task-row-billing">{billingLabel(metadata)}</p> : null}
        {job.status === "failed" ? (
          <p className="task-row-error" title={job.error_message || "任务执行失败"}>
            {job.error_code || "JOB_EXECUTION_FAILED"} · {job.error_message || "任务执行失败"}
          </p>
        ) : null}
      </div>
      <JobStatusBadge status={job.status} />
      <div className="task-row-actions">
        {job.status === "failed" ? (
          <IconButton label="返回工具重试" onClick={() => onRetry(job)}>
            <RotateCcw size={18} strokeWidth={2.2} />
          </IconButton>
        ) : null}
        <JobAssetActions
          deleteDisabled={job.status === "pending" || job.status === "running"}
          job={job}
          outputAsset={outputAsset}
          downloading={isDownloading}
          deleting={isDeleting}
          onDownload={onDownload}
          onDelete={onDelete}
        />
      </div>
    </article>
  );
}

function billingLabel(metadata: JobListMetadata) {
  if (metadata.credits === 0) return "费用：免费";
  if (metadata.reservation_status === "charged") return `费用：${metadata.credits} 积分 · 已扣除`;
  if (metadata.reservation_status === "released") return `费用：${metadata.credits} 积分 · 已退回`;
  return `费用：${metadata.credits} 积分 · 已冻结`;
}

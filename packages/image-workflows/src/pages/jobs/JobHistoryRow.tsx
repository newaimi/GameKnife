import type { TFunction } from "@gameknife/i18n";
import type { JobResponse, OutputAssetRef } from "@gameknife/shared-types";
import { useTranslation } from "react-i18next";
import { JobAssetActions } from "../../components/JobAssetActions";
import { RotateCcw } from "lucide-react";
import { IconButton } from "@gameknife/ui-kit";
import type { JobListMetadata } from "./CommunityJobsPage";
import { JobStatusBadge } from "../../components/JobStatusBadge";
import { useObjectUrl } from "../../utils/objectUrl";
import { readFirstJobOutputAsset } from "../../utils/jobs";
import {
  formatAbsoluteTime,
  formatJobFileMeta,
  readJobDisplayName,
  readJobInitial,
  readJobThumbnailPath,
  readJobTitle,
  type JobPresentationResolver,
} from "./jobHistory";

export function JobHistoryRow({
  deletingJobId,
  downloadingAssetId,
  job,
  jobPresentationResolver,
  onDelete,
  onDownload,
  onRetry,
  metadata,
}: {
  deletingJobId: string;
  downloadingAssetId: string;
  job: JobResponse;
  jobPresentationResolver?: JobPresentationResolver;
  onDelete: (job: JobResponse) => void | Promise<void>;
  onDownload: (job: JobResponse, asset: OutputAssetRef) => void | Promise<void>;
  onRetry: (job: JobResponse) => void;
  metadata?: JobListMetadata;
}) {
  const { i18n, t } = useTranslation("jobs");
  const presentation = jobPresentationResolver?.(job);
  const displayName = presentation?.displayName ?? readJobDisplayName(job, t);
  const thumbnailUrl = useObjectUrl(
    presentation?.thumbnailPath ?? readJobThumbnailPath(job),
  );
  const outputAsset = readFirstJobOutputAsset(job);
  const isDownloading = outputAsset ? downloadingAssetId === outputAsset.id : false;
  const isDeleting = deletingJobId === job.id;

  return (
    <article className="task-row">
      <div className="job-thumb task-row-thumb">
        {thumbnailUrl ? <img src={thumbnailUrl} alt={displayName} /> : <span>{presentation?.initial ?? readJobInitial(job, t)}</span>}
      </div>
      <div className="task-row-main">
        <div>
          <strong title={displayName}>{displayName}</strong>
          <span>{presentation?.title ?? readJobTitle(job, t)}</span>
        </div>
        <p>
          {presentation?.fileMeta ?? formatJobFileMeta(job, t)} · {formatAbsoluteTime(job.updated_at, i18n.resolvedLanguage ?? i18n.language)}
        </p>
        {metadata ? <p className="task-row-billing">{billingLabel(metadata, t)}</p> : null}
        {job.status === "failed" ? (
          <p className="task-row-error" title={job.error_message || t("status.executionFailed")}>
            {job.error_code || "JOB_EXECUTION_FAILED"} · {job.error_message || t("status.executionFailed")}
          </p>
        ) : null}
      </div>
      <JobStatusBadge status={job.status} />
      <div className="task-row-actions">
        {job.status === "failed" ? (
          <IconButton label={t("actions.retry")} onClick={() => onRetry(job)}>
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

function billingLabel(metadata: JobListMetadata, t: TFunction) {
  if (metadata.credits === 0) return t("billing.free");
  return t("billing.summary", {
    credits: metadata.credits,
    state: t(`billing.${metadata.reservation_status}`),
  });
}

import type { JobResponse, OutputAssetRef } from "@gameknife/shared-types";
import { JobAssetActions } from "../../components/JobAssetActions";
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
      </div>
      <JobStatusBadge status={job.status} />
      <JobAssetActions job={job} outputAsset={outputAsset} downloading={isDownloading} deleting={isDeleting} onDownload={onDownload} onDelete={onDelete} />
    </article>
  );
}

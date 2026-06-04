import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Download, Trash2 } from "lucide-react";
import { gameKnifeApiClient } from "@gameknife/api-client";
import type { JobResponse, OutputAssetRef } from "@gameknife/shared-types";
import { useObjectUrl } from "../../utils/objectUrl";
import { readFirstJobOutputAsset } from "../../utils/jobs";
import { readMessage } from "../../utils/errors";
import { downloadJobAsset, formatJobFileMeta, formatJobStatus, formatRelativeTime, readJobDisplayName, readJobInitial, readJobThumbnailPath } from "./jobHistory";

const RECENT_JOB_PAGE_SIZE = 4;

export function RecentJobs({ refreshKey = "" }: { refreshKey?: string | number }) {
  const navigate = useNavigate();
  const [jobs, setJobs] = useState<JobResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [downloadingAssetId, setDownloadingAssetId] = useState("");
  const [deletingJobId, setDeletingJobId] = useState("");
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setError("");

    void gameKnifeApiClient
      .listJobHistory({ page: 1, pageSize: RECENT_JOB_PAGE_SIZE, category: "all", downloadable: true })
      .then((result) => {
        if (!cancelled) {
          setJobs(result.items);
          setTotal(result.total);
        }
      })
      .catch((exc) => {
        if (!cancelled) {
          setJobs([]);
          setTotal(0);
          setError(readMessage(exc));
        }
      });

    return () => {
      cancelled = true;
    };
  }, [refreshKey, reloadKey]);

  async function handleDownload(job: JobResponse, asset: OutputAssetRef) {
    setError("");
    setDownloadingAssetId(asset.id);
    try {
      await downloadJobAsset(job, asset);
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setDownloadingAssetId("");
    }
  }

  async function handleDelete(job: JobResponse) {
    if (["pending", "running"].includes(job.status)) {
      return;
    }
    if (!window.confirm("删除后会移除这条任务记录和对应生成文件，是否继续？")) {
      return;
    }

    setError("");
    setDeletingJobId(job.id);
    try {
      await gameKnifeApiClient.deleteJob(job.id);
      setReloadKey((current) => current + 1);
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setDeletingJobId("");
    }
  }

  return (
    <section className="recent">
      <div className="section-title">
        <h2>最近处理</h2>
        {total > RECENT_JOB_PAGE_SIZE ? (
          <button className="recent-view-all" type="button" onClick={() => navigate("/jobs")}>
            查看全部 ›
          </button>
        ) : (
          <span>{total} 个任务</span>
        )}
      </div>
      <div className="recent-grid">
        {jobs.length ? (
          jobs.map((job) => (
            <RecentJobCard deletingJobId={deletingJobId} downloadingAssetId={downloadingAssetId} job={job} key={job.id} onDelete={handleDelete} onDownload={handleDownload} />
          ))
        ) : (
          <p className="muted">暂无任务。</p>
        )}
      </div>
      {error ? <p className="recent-error">{error}</p> : null}
    </section>
  );
}

function RecentJobCard({
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
  const canDelete = !["pending", "running"].includes(job.status);
  const isDownloading = outputAsset ? downloadingAssetId === outputAsset.id : false;
  const isDeleting = deletingJobId === job.id;

  return (
    <article className="recent-item">
      <div className="recent-thumb">
        {thumbnailUrl ? <img src={thumbnailUrl} alt={readJobDisplayName(job)} /> : <span>{readJobInitial(job)}</span>}
      </div>
      <div className="recent-info">
        <strong title={readJobDisplayName(job)}>{readJobDisplayName(job)}</strong>
        <p>{formatJobFileMeta(job)}</p>
        <p>
          {formatJobStatus(job.status)} · {formatRelativeTime(job.updated_at)}
        </p>
      </div>
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
        <button
          className="recent-icon-button danger"
          type="button"
          title={canDelete ? "删除任务" : "任务处理中，完成后才能删除"}
          disabled={!canDelete || isDeleting}
          onClick={() => void onDelete(job)}
        >
          <Trash2 size={18} strokeWidth={2.2} />
        </button>
      </div>
    </article>
  );
}

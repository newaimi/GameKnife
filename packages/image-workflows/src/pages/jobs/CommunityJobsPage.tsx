import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";
import { gameKnifeApiClient } from "@gameknife/api-client";
import type { JobPageResponse, JobResponse, OutputAssetRef } from "@gameknife/shared-types";
import { Button, FeedbackMessage } from "@gameknife/ui-kit";
import { readMessage } from "../../utils/errors";
import { DatePickerField } from "./DatePickerField";
import { JobHistoryRow } from "./JobHistoryRow";
import {
  JOB_CATEGORY_OPTIONS,
  JOB_LIST_PAGE_SIZE,
  dateInputToEndIso,
  dateInputToStartIso,
  downloadJobAsset,
  type JobCategoryOption,
  type JobPresentationResolver,
} from "./jobHistory";
import { readJobRetryRoute } from "../../utils/jobRetry";
import { useImageAssetSession } from "../../context/ImageAssetSession";
import { saveVideoToSequenceTransfer } from "../../workspaces/sequence/videoToSequenceTransfer";

export interface JobListMetadata {
  credits: number;
  reservation_status: "frozen" | "charged" | "released";
}

export function CommunityJobsPage({
  jobCategoryOptions = JOB_CATEGORY_OPTIONS,
  jobPresentationResolver,
  loadJobMetadata,
}: {
  jobCategoryOptions?: JobCategoryOption[];
  jobPresentationResolver?: JobPresentationResolver;
  loadJobMetadata?: (jobIds: string[]) => Promise<Record<string, JobListMetadata>>;
} = {}) {
  const navigate = useNavigate();
  const imageSession = useImageAssetSession();
  const { t } = useTranslation("jobs");
  const [category, setCategory] = useState("all");
  const [statusFilter, setStatusFilter] = useState<"all" | JobResponse["status"]>("all");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [page, setPage] = useState(1);
  const [jobPage, setJobPage] = useState<JobPageResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [downloadingAssetId, setDownloadingAssetId] = useState("");
  const [deletingJobId, setDeletingJobId] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [metadata, setMetadata] = useState<Record<string, JobListMetadata>>({});
  const totalPages = Math.max(1, Math.ceil((jobPage?.total ?? 0) / JOB_LIST_PAGE_SIZE));

  useEffect(() => {
    setPage(1);
  }, [category, startDate, endDate, statusFilter]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");

    void gameKnifeApiClient
      .listJobHistory({
        page,
        pageSize: JOB_LIST_PAGE_SIZE,
        category,
        createdFrom: dateInputToStartIso(startDate),
        createdTo: dateInputToEndIso(endDate),
        deliveryOnly: true,
        status: statusFilter === "all" ? undefined : statusFilter,
      })
      .then(async (result) => {
        if (!cancelled) {
          setJobPage(result);
          if (loadJobMetadata && result.items.length) {
            try {
              const nextMetadata = await loadJobMetadata(result.items.map((job) => job.id));
              if (!cancelled) {
                setMetadata(nextMetadata);
              }
            } catch {
              // Billing metadata is an optional Commercial enrichment. A transient billing read must not hide the
              // authoritative public Job list or its retry actions.
              if (!cancelled) {
                setMetadata({});
              }
            }
          } else {
            setMetadata({});
          }
        }
      })
      .catch((exc) => {
        if (!cancelled) {
          setError(readMessage(exc));
          setJobPage({ items: [], total: 0, page, page_size: JOB_LIST_PAGE_SIZE });
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [category, endDate, loadJobMetadata, page, reloadKey, startDate, statusFilter]);

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
    if (!window.confirm(t("deleteConfirm"))) {
      return;
    }

    setDeletingJobId(job.id);
    setError("");
    try {
      await gameKnifeApiClient.deleteJob(job.id);
      setReloadKey((current) => current + 1);
    } catch (exc) {
      setError(readMessage(exc));
    } finally {
      setDeletingJobId("");
    }
  }

  function handleRetry(job: JobResponse) {
    const presentation = jobPresentationResolver?.(job);
    const route = presentation?.retryRoute ?? readJobRetryRoute(job);
    if (!route) {
      return;
    }
    if (job.input_asset_id && job.input_mime_type?.startsWith("image/") && job.input_filename && job.input_size_bytes != null) {
      imageSession?.setImageAsset({
        id: job.input_asset_id,
        filename: job.input_filename,
        mime_type: job.input_mime_type,
        size_bytes: job.input_size_bytes,
        url: `/api/assets/${job.input_asset_id}`,
      });
    }
    if (job.input_asset_id && job.type === "sequence_video_to_frames" && job.input_filename && job.input_mime_type && job.input_size_bytes != null) {
      saveVideoToSequenceTransfer({
        asset: {
          id: job.input_asset_id,
          filename: job.input_filename,
          mime_type: job.input_mime_type,
          size_bytes: job.input_size_bytes,
          url: `/api/assets/${job.input_asset_id}`,
        },
        action: "walk_down",
      });
    }
    navigate(route);
  }

  return (
    <section className="task-list-page">
      <div className="page-heading task-list-heading">
        <div>
          <p className="eyebrow">{t("eyebrow")}</p>
          <h1>{t("title")}</h1>
          <p>{t("description")}</p>
        </div>
        <Button onClick={() => setReloadKey((current) => current + 1)}>
          <RefreshCw size={18} />
          {t("refresh")}
        </Button>
      </div>

      <section className="task-filter-card">
        <div className="task-filter-tabs" aria-label={t("filterLabel")}>
          {jobCategoryOptions.map((option) => (
            <button key={option.value} className={category === option.value ? "active" : ""} type="button" onClick={() => setCategory(option.value)}>
              <strong>{option.translationKey ? t(`categories.${option.translationKey}.label`) : option.label}</strong>
              <span>{option.translationKey ? t(`categories.${option.translationKey}.note`) : option.note}</span>
            </button>
          ))}
        </div>
        <div className="task-date-filters">
          <label className="task-status-filter">
            <span>{t("statusFilter")}</span>
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}>
              <option value="all">{t("categories.all.label")}</option>
              <option value="pending">{t("status.queued")}</option>
              <option value="running">{t("status.running")}</option>
              <option value="success">{t("status.succeeded")}</option>
              <option value="failed">{t("status.failed")}</option>
            </select>
          </label>
          <DatePickerField label={t("startTime")} value={startDate} onChange={setStartDate} />
          <DatePickerField label={t("endTime")} value={endDate} onChange={setEndDate} />
          <Button
            size="small"
            onClick={() => {
              setStartDate("");
              setEndDate("");
            }}
          >
            {t("clearTime")}
          </Button>
        </div>
      </section>

      <section className="task-table-card">
        <div className="task-table-summary">
          <span>{loading ? t("loading") : t("resultCount", { count: jobPage?.total ?? 0 })}</span>
          <span>{t("page", { current: Math.min(page, totalPages), total: totalPages })}</span>
        </div>
        {error ? <FeedbackMessage tone="danger">{error}</FeedbackMessage> : null}
        <div className="task-table">
          {jobPage?.items.length ? (
            jobPage.items.map((job) => (
              <JobHistoryRow
                deletingJobId={deletingJobId}
                downloadingAssetId={downloadingAssetId}
                job={job}
                jobPresentationResolver={jobPresentationResolver}
                key={job.id}
                metadata={metadata[job.id]}
                onDelete={handleDelete}
                onDownload={handleDownload}
                onRetry={handleRetry}
              />
            ))
          ) : (
            <div className="task-empty">
              <strong>{loading ? t("loadingJobs") : t("empty")}</strong>
              <span>{t("emptyHint")}</span>
            </div>
          )}
        </div>
        <div className="task-pagination">
          <Button size="small" disabled={page <= 1 || loading} onClick={() => setPage((current) => Math.max(1, current - 1))}>
            {t("previousPage")}
          </Button>
          <Button size="small" disabled={page >= totalPages || loading} onClick={() => setPage((current) => current + 1)}>
            {t("nextPage")}
          </Button>
        </div>
      </section>
    </section>
  );
}

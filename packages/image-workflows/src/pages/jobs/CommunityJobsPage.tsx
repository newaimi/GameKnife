import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";
import { gameKnifeApiClient } from "@gameknife/api-client";
import type { JobPageResponse, JobResponse, OutputAssetRef } from "@gameknife/shared-types";
import { Button, FeedbackMessage } from "@gameknife/ui-kit";
import { readMessage } from "../../utils/errors";
import { DatePickerField } from "./DatePickerField";
import { JobHistoryRow } from "./JobHistoryRow";
import { JOB_CATEGORY_OPTIONS, JOB_LIST_PAGE_SIZE, dateInputToEndIso, dateInputToStartIso, downloadJobAsset } from "./jobHistory";

export function CommunityJobsPage() {
  const { t } = useTranslation("jobs");
  const [category, setCategory] = useState("all");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [page, setPage] = useState(1);
  const [jobPage, setJobPage] = useState<JobPageResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [downloadingAssetId, setDownloadingAssetId] = useState("");
  const [deletingJobId, setDeletingJobId] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const totalPages = Math.max(1, Math.ceil((jobPage?.total ?? 0) / JOB_LIST_PAGE_SIZE));

  useEffect(() => {
    setPage(1);
  }, [category, startDate, endDate]);

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
        downloadable: true,
      })
      .then((result) => {
        if (!cancelled) {
          setJobPage(result);
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
  }, [category, endDate, page, reloadKey, startDate]);

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
          {JOB_CATEGORY_OPTIONS.map((option) => (
            <button key={option.value} className={category === option.value ? "active" : ""} type="button" onClick={() => setCategory(option.value)}>
              <strong>{t(`categories.${option.translationKey}.label`)}</strong>
              <span>{t(`categories.${option.translationKey}.note`)}</span>
            </button>
          ))}
        </div>
        <div className="task-date-filters">
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
            jobPage.items.map((job) => <JobHistoryRow deletingJobId={deletingJobId} downloadingAssetId={downloadingAssetId} job={job} key={job.id} onDelete={handleDelete} onDownload={handleDownload} />)
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

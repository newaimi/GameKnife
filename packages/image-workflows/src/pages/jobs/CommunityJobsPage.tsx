import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { gameKnifeApiClient } from "@gameknife/api-client";
import type { JobPageResponse, JobResponse, OutputAssetRef } from "@gameknife/shared-types";
import { readMessage } from "../../utils/errors";
import { DatePickerField } from "./DatePickerField";
import { JobHistoryRow } from "./JobHistoryRow";
import { JOB_CATEGORY_OPTIONS, JOB_LIST_PAGE_SIZE, dateInputToEndIso, dateInputToStartIso, downloadJobAsset } from "./jobHistory";

export function CommunityJobsPage() {
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
    if (!window.confirm("删除后会移除这条任务记录和对应生成文件，是否继续？")) {
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
          <p className="eyebrow">任务历史</p>
          <h1>可下载结果</h1>
          <p>这里只展示已经生成文件的任务，识别素材框、刷新框选这类中间步骤不会混进来。</p>
        </div>
        <button className="ghost" type="button" onClick={() => setReloadKey((current) => current + 1)}>
          <RefreshCw size={18} />
          刷新
        </button>
      </div>

      <section className="task-filter-card">
        <div className="task-filter-tabs" aria-label="任务类型筛选">
          {JOB_CATEGORY_OPTIONS.map((option) => (
            <button key={option.value} className={category === option.value ? "active" : ""} type="button" onClick={() => setCategory(option.value)}>
              <strong>{option.label}</strong>
              <span>{option.note}</span>
            </button>
          ))}
        </div>
        <div className="task-date-filters">
          <DatePickerField label="开始时间" value={startDate} onChange={setStartDate} />
          <DatePickerField label="结束时间" value={endDate} onChange={setEndDate} />
          <button
            className="ghost compact"
            type="button"
            onClick={() => {
              setStartDate("");
              setEndDate("");
            }}
          >
            清空时间
          </button>
        </div>
      </section>

      <section className="task-table-card">
        <div className="task-table-summary">
          <span>{loading ? "正在加载..." : `共 ${jobPage?.total ?? 0} 个可下载结果`}</span>
          <span>
            第 {Math.min(page, totalPages)} / {totalPages} 页
          </span>
        </div>
        {error ? <p className="recent-error">{error}</p> : null}
        <div className="task-table">
          {jobPage?.items.length ? (
            jobPage.items.map((job) => <JobHistoryRow deletingJobId={deletingJobId} downloadingAssetId={downloadingAssetId} job={job} key={job.id} onDelete={handleDelete} onDownload={handleDownload} />)
          ) : (
            <div className="task-empty">
              <strong>{loading ? "正在加载任务..." : "没有符合条件的任务"}</strong>
              <span>可以换一个任务类型或时间范围再试。</span>
            </div>
          )}
        </div>
        <div className="task-pagination">
          <button className="ghost compact" type="button" disabled={page <= 1 || loading} onClick={() => setPage((current) => Math.max(1, current - 1))}>
            上一页
          </button>
          <button className="ghost compact" type="button" disabled={page >= totalPages || loading} onClick={() => setPage((current) => current + 1)}>
            下一页
          </button>
        </div>
      </section>
    </section>
  );
}

import { useMemo } from "react";
import { Download } from "lucide-react";
import type { AssetResponse, JobResponse, OutputAssetRef } from "@gameknife/shared-types";
import { downloadJobOutputAsset, downloadOutputAsset } from "../utils/assets";
import { readJobOutputAssets } from "../utils/jobs";
import { formatJobStatus, readJobTitle } from "../utils/jobPresentation";

export function JobResult({ job }: { job: JobResponse | null }) {
  const outputAssets = useMemo(() => readOutputAssets(job), [job]);
  if (!job) {
    return null;
  }
  return (
    <div className="job-result">
      <span>
        {readJobTitle(job)} · {formatJobStatus(job.status)}
      </span>
      {job.error_message ? <p className="error-text">{job.error_message}</p> : null}
      {outputAssets.map((asset) => (
        <button className="ghost" key={asset.id} onClick={() => void downloadJobOutputAsset(job, asset)} type="button">
          <Download size={18} />
          下载
        </button>
      ))}
    </div>
  );
}

export function AssetSaveResult({ asset }: { asset: AssetResponse | null }) {
  if (!asset) {
    return null;
  }
  return (
    <div className="job-result">
      <span>{asset.filename}</span>
      <button className="ghost" onClick={() => void downloadOutputAsset({ id: asset.id, url: asset.url }, asset.filename)} type="button">
        <Download size={18} />
        下载
      </button>
    </div>
  );
}

export function StatusLine({ error, job }: { error: string; job: JobResponse | null }) {
  if (error) {
    return <p className="error-text">{error}</p>;
  }
  if (!job) {
    return null;
  }
  return <span className="status-text">{formatJobStatus(job.status)}</span>;
}

function readOutputAssets(job: JobResponse | null): OutputAssetRef[] {
  return readJobOutputAssets(job);
}

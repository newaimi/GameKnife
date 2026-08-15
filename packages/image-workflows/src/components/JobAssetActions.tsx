import { Download, Trash2 } from "lucide-react";
import type { JobResponse, OutputAssetRef } from "@gameknife/shared-types";
import { IconButton } from "@gameknife/ui-kit";

export function JobAssetActions({
  job,
  outputAsset,
  downloading,
  deleting,
  deleteDisabled,
  onDownload,
  onDelete,
}: {
  job: JobResponse;
  outputAsset?: OutputAssetRef;
  downloading: boolean;
  deleting: boolean;
  deleteDisabled?: boolean;
  onDownload: (job: JobResponse, asset: OutputAssetRef) => void | Promise<void>;
  onDelete: (job: JobResponse) => void | Promise<void>;
}) {
  return (
    <div className="recent-actions">
      <IconButton
        label={outputAsset ? "下载结果" : "当前任务没有可下载文件"}
        disabled={!outputAsset || downloading}
        onClick={() => outputAsset && void onDownload(job, outputAsset)}
      >
        <Download size={18} strokeWidth={2.2} />
      </IconButton>
      <IconButton
        label={deleteDisabled ? "任务处理中，完成后才能删除" : "删除任务"}
        variant="danger"
        disabled={deleteDisabled || deleting}
        onClick={() => void onDelete(job)}
      >
        <Trash2 size={18} strokeWidth={2.2} />
      </IconButton>
    </div>
  );
}

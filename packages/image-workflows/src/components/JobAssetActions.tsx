import { Download, Trash2 } from "lucide-react";
import type { JobResponse, OutputAssetRef } from "@gameknife/shared-types";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation("jobs");
  return (
    <div className="job-asset-actions">
      <IconButton
        label={outputAsset ? t("actions.download") : t("actions.noDownload")}
        disabled={!outputAsset || downloading}
        onClick={() => outputAsset && void onDownload(job, outputAsset)}
      >
        <Download size={18} strokeWidth={2.2} />
      </IconButton>
      <IconButton
        label={deleteDisabled ? t("actions.deleteWhileRunning") : t("actions.delete")}
        variant="danger"
        disabled={deleteDisabled || deleting}
        onClick={() => void onDelete(job)}
      >
        <Trash2 size={18} strokeWidth={2.2} />
      </IconButton>
    </div>
  );
}

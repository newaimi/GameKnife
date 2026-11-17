import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import type { TFunction } from "@gameknife/i18n";
import type { JobResponse } from "@gameknife/shared-types";
import { Button } from "@gameknife/ui-kit";
import type { FailureDialogState } from "../types/failure";
import { readJobTitle } from "../utils/jobPresentation";

export function FailureDialog({ dialog, onClose }: { dialog: FailureDialogState; onClose: () => void }) {
  const { t } = useTranslation("workbench");
  const dialogId = "task-failure-dialog-title";
  const modal = (
    <div className="failure-dialog-backdrop" role="presentation" onClick={onClose}>
      <section className="failure-dialog" role="dialog" aria-modal="true" aria-labelledby={dialogId} onClick={(event) => event.stopPropagation()}>
        <div className="failure-dialog-title">
          <div>
            <span>{t("failure.label")}</span>
            <strong id={dialogId}>{dialog.title}</strong>
          </div>
          <Button size="small" onClick={onClose}>
            {t("failure.close")}
          </Button>
        </div>
        <p>{dialog.message}</p>
        <pre>{dialog.detail}</pre>
      </section>
    </div>
  );

  // Keep failure dialogs outside the workbench transform context so zoom and pan never distort error details.
  return createPortal(modal, document.body);
}

export function readJobFailureDialog(job: JobResponse, tWorkbench: TFunction, tJobs: TFunction): FailureDialogState {
  const detail = job.error_message?.trim() || tWorkbench("failure.unknownBackendError");
  const jobTitle = readJobTitle(job, tJobs);
  return {
    title: tWorkbench("failure.jobTitle", { title: jobTitle }),
    message: tWorkbench("failure.jobMessage"),
    detail: tWorkbench("failure.jobDetail", { id: job.id, detail }),
  };
}

export function readRequestFailureDialog(title: string, message: string, error: unknown, t: TFunction): FailureDialogState {
  return {
    title,
    message,
    detail: error instanceof Error ? error.message : t("failure.request"),
  };
}

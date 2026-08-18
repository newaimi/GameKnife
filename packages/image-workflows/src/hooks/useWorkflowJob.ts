import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import type { JobResponse } from "@gameknife/shared-types";
import { readJobFailureDialog, readRequestFailureDialog } from "../components/FailureDialog";
import type { FailureDialogState } from "../types/failure";
import { readMessage } from "../utils/errors";
import { waitForJob, type JobPollingOptions } from "../utils/jobs";

export interface WorkflowJobRunOptions<TJob extends JobResponse> {
  createJob: () => Promise<JobResponse>;
  failureTitle: string;
  failureMessage: string;
  polling?: JobPollingOptions;
  mapJob?: (job: JobResponse) => TJob;
  onSuccess?: (job: TJob) => void;
  onFinished?: (job: TJob) => void;
}

export function useWorkflowJob<TJob extends JobResponse = JobResponse>() {
  const { t: tWorkbench } = useTranslation("workbench");
  const { t: tJobs } = useTranslation("jobs");
  const [job, setJob] = useState<TJob | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [failureDialog, setFailureDialog] = useState<FailureDialogState | null>(null);

  const resetJob = useCallback(() => {
    setJob(null);
    setError("");
    setFailureDialog(null);
  }, []);

  const runJob = useCallback(async (options: WorkflowJobRunOptions<TJob>) => {
    setBusy(true);
    setError("");
    setFailureDialog(null);
    try {
      const created = await options.createJob();
      // Publish the created job immediately so the queue state and job ID are visible during long-running work.
      // Replace it with the final response after polling to keep the workbench responsive without duplicating state.
      setJob(options.mapJob ? options.mapJob(created) : (created as TJob));
      const polled = await waitForJob(created.id, options.polling);
      const finished = options.mapJob ? options.mapJob(polled) : (polled as TJob);
      setJob(finished);
      options.onFinished?.(finished);
      if (finished.status === "success") {
        options.onSuccess?.(finished);
      } else if (finished.status === "failed") {
        setFailureDialog(readJobFailureDialog(finished, tWorkbench, tJobs));
      }
      return finished;
    } catch (exc) {
      setError(readMessage(exc));
      setFailureDialog(readRequestFailureDialog(options.failureTitle, options.failureMessage, exc, tWorkbench));
      return null;
    } finally {
      setBusy(false);
    }
  }, [tJobs, tWorkbench]);

  return {
    job,
    setJob,
    busy,
    error,
    setError,
    failureDialog,
    setFailureDialog,
    runJob,
    resetJob,
  };
}

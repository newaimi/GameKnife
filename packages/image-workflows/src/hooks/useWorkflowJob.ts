import { useCallback, useState } from "react";
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
      // 任务创建成功后立即写入页面状态，用户可以马上看到队列状态和任务编号。
      // 轮询完成后再覆盖为最终结果，避免长任务期间工作台看起来像没有响应。
      setJob(options.mapJob ? options.mapJob(created) : (created as TJob));
      const polled = await waitForJob(created.id, options.polling);
      const finished = options.mapJob ? options.mapJob(polled) : (polled as TJob);
      setJob(finished);
      options.onFinished?.(finished);
      if (finished.status === "success") {
        options.onSuccess?.(finished);
      } else if (finished.status === "failed") {
        setFailureDialog(readJobFailureDialog(finished));
      }
      return finished;
    } catch (exc) {
      setError(readMessage(exc));
      setFailureDialog(readRequestFailureDialog(options.failureTitle, options.failureMessage, exc));
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

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

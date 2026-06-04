import type { ReactNode } from "react";
import type { JobResponse } from "@gameknife/shared-types";
import { FailureDialog } from "./FailureDialog";
import { JobResult } from "./JobResult";
import { RecentJobs } from "../pages/jobs/RecentJobs";
import type { FailureDialogState } from "../types/failure";

interface WorkflowResultFooterProps {
  job: JobResponse | null;
  refreshKey: string;
  failureDialog: FailureDialogState | null;
  onCloseFailure: () => void;
  children?: ReactNode;
}

export function WorkflowResultFooter({ job, refreshKey, failureDialog, onCloseFailure, children }: WorkflowResultFooterProps) {
  const hasResultContent = Boolean(job || children);

  return (
    <>
      {hasResultContent ? (
        // 结果面板只在有任务或额外结果内容时出现。
        // 空任务状态直接接最近处理，避免工作台中间留下无意义的空白容器。
        <section className="workspace-result-panel">
          {children}
          <JobResult job={job} />
        </section>
      ) : null}
      <RecentJobs refreshKey={refreshKey} />
      {failureDialog ? <FailureDialog dialog={failureDialog} onClose={onCloseFailure} /> : null}
    </>
  );
}

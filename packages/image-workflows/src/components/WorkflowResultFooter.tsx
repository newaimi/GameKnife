import { FailureDialog } from "./FailureDialog";
import { RecentJobs } from "../pages/jobs/RecentJobs";
import type { FailureDialogState } from "../types/failure";

interface WorkflowResultFooterProps {
  refreshKey: string;
  failureDialog: FailureDialogState | null;
  onCloseFailure: () => void;
}

export function WorkflowResultFooter({ refreshKey, failureDialog, onCloseFailure }: WorkflowResultFooterProps) {
  return (
    <>
      <RecentJobs refreshKey={refreshKey} />
      {failureDialog ? <FailureDialog dialog={failureDialog} onClose={onCloseFailure} /> : null}
    </>
  );
}

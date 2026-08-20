import { createContext, useContext, type ReactNode } from "react";
import type { TaskSubmissionOptions } from "@gameknife/api-client";
import type { JobResponse } from "@gameknife/shared-types";

export interface WorkflowSubmissionRequest<TJob extends JobResponse = JobResponse> {
  jobType: string;
  parameters: object;
  idempotencyPayload: unknown;
  createJob: (submission?: TaskSubmissionOptions) => Promise<TJob>;
}

export interface WorkflowSubmissionProviderValue {
  submit<TJob extends JobResponse>(request: WorkflowSubmissionRequest<TJob>): Promise<TJob>;
  onJobFinished?(job: JobResponse): void;
}

const directSubmissionProvider: WorkflowSubmissionProviderValue = {
  submit<TJob extends JobResponse>(request: WorkflowSubmissionRequest<TJob>) {
    return request.createJob();
  },
};

const WorkflowSubmissionContext = createContext<WorkflowSubmissionProviderValue>(directSubmissionProvider);

export function WorkflowSubmissionProvider({ value, children }: { value?: WorkflowSubmissionProviderValue; children: ReactNode }) {
  // Community omits a value and submits directly. Commercial shells can inject quote and idempotency handling without changing tool pages.
  return <WorkflowSubmissionContext.Provider value={value ?? directSubmissionProvider}>{children}</WorkflowSubmissionContext.Provider>;
}

export function useWorkflowSubmission(): WorkflowSubmissionProviderValue {
  return useContext(WorkflowSubmissionContext);
}

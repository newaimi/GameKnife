export type ManualEditSource = {
  name: string;
  url: string;
  blob?: Blob;
  sourceFileId?: string;
  sourceContext?: string;
  revokeObjectUrl?: boolean;
};

export type ManualEditTransferRecord = {
  id: string;
  name: string;
  blob: Blob;
  sourceFileId?: string;
  sourceContext?: string;
  createdAt: number;
};

export type { FailureDialogState } from "./failure";

import { FailureDialog } from "./FailureDialog";
import type { FailureDialogState } from "../types/failure";

interface WorkflowFailureDialogProps {
  /** Dialog state created by a failed workflow write. Null keeps the workbench layout untouched. */
  failureDialog: FailureDialogState | null;
  /** State reset owned by the workflow that created the failure. */
  onCloseFailure: () => void;
}

/**
 * Renders workflow failures consistently without bringing job history back into the fixed workbench viewport.
 * Each workflow supplies only its state and reset callback.
 */
export function WorkflowFailureDialog({ failureDialog, onCloseFailure }: WorkflowFailureDialogProps) {
  return failureDialog ? <FailureDialog dialog={failureDialog} onClose={onCloseFailure} /> : null;
}

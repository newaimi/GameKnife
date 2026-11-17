/**
 * Inputs for the manual editor action bar come directly from document, permission, save, and history state.
 * Keeping the calculation free of component state makes empty, read-only, and saving cases independently testable.
 */
export type ManualEditorActionStateInput = {
  hasSource: boolean;
  canWrite: boolean;
  saving: boolean;
  canUndo: boolean;
  canRedo: boolean;
};

/** Disabled states for actions in the manual editor toolbar. */
export type ManualEditorActionState = {
  uploadDisabled: boolean;
  undoDisabled: boolean;
  redoDisabled: boolean;
  saveDisabled: boolean;
  exportDisabled: boolean;
};

/**
 * Calculates each action from its actual dependencies. Import needs write permission, export needs a document,
 * and save needs a document, permission, and no request in progress.
 */
export function readManualEditorActionState({
  hasSource,
  canWrite,
  saving,
  canUndo,
  canRedo,
}: ManualEditorActionStateInput): ManualEditorActionState {
  return {
    uploadDisabled: !canWrite,
    undoDisabled: !canUndo,
    redoDisabled: !canRedo,
    saveDisabled: !hasSource || saving || !canWrite,
    exportDisabled: !hasSource,
  };
}

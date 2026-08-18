/** Store browser scheduling handles in mutable refs shared by React lifecycle and event handlers. */
export type ManualEditorScheduleRef = {
  current: number | null;
};

/**
 * Clear pending animation frames and status timers for the manual editor.
 * React StrictMode performs an extra effect cleanup and rerun in development. Clearing each ref together with its
 * browser task prevents stale handles from blocking later brush and selection redraws.
 */
export function clearManualEditorScheduledWork(
  renderFrameRef: ManualEditorScheduleRef,
  statusTimerRef: ManualEditorScheduleRef,
  cancelRenderFrame: (frameId: number) => void,
  clearStatusTimer: (timerId: number) => void,
) {
  const frameId = renderFrameRef.current;
  renderFrameRef.current = null;
  if (frameId !== null) {
    cancelRenderFrame(frameId);
  }

  const timerId = statusTimerRef.current;
  statusTimerRef.current = null;
  if (timerId !== null) {
    clearStatusTimer(timerId);
  }
}

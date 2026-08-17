/** 浏览器调度句柄使用可变引用保存，便于 React 生命周期和事件处理函数共享。 */
export type ManualEditorScheduleRef = {
  current: number | null;
};

/**
 * 清理手动编辑器尚未执行的动画帧和状态定时器。
 * React StrictMode 会在开发环境额外执行一次 effect 的清理和重新执行；取消浏览器任务后必须同步清空引用，
 * 否则后续调度逻辑会把已经失效的编号误认为仍在执行，画笔和选区都无法触发可视重绘。
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

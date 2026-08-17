import assert from "node:assert/strict";
import test from "node:test";
import { clearManualEditorScheduledWork } from "../dist/workspaces/manual-edit/manualEditorScheduling.js";

test("StrictMode 清理后释放手动编辑器调度引用并允许再次调度", () => {
  const renderFrameRef = { current: 17 };
  const statusTimerRef = { current: 23 };
  const cancelledFrames = [];
  const clearedTimers = [];

  clearManualEditorScheduledWork(
    renderFrameRef,
    statusTimerRef,
    (frameId) => cancelledFrames.push(frameId),
    (timerId) => clearedTimers.push(timerId),
  );

  assert.equal(renderFrameRef.current, null);
  assert.equal(statusTimerRef.current, null);
  assert.deepEqual(cancelledFrames, [17]);
  assert.deepEqual(clearedTimers, [23]);

  // StrictMode 会在清理后重新执行 effect；新的浏览器任务必须能写入并再次被正常回收。
  renderFrameRef.current = 31;
  statusTimerRef.current = 47;
  clearManualEditorScheduledWork(
    renderFrameRef,
    statusTimerRef,
    (frameId) => cancelledFrames.push(frameId),
    (timerId) => clearedTimers.push(timerId),
  );

  assert.equal(renderFrameRef.current, null);
  assert.equal(statusTimerRef.current, null);
  assert.deepEqual(cancelledFrames, [17, 31]);
  assert.deepEqual(clearedTimers, [23, 47]);
});

test("没有待执行任务时清理函数不调用浏览器取消接口", () => {
  const renderFrameRef = { current: null };
  const statusTimerRef = { current: null };
  let cancelCount = 0;

  clearManualEditorScheduledWork(
    renderFrameRef,
    statusTimerRef,
    () => {
      cancelCount += 1;
    },
    () => {
      cancelCount += 1;
    },
  );

  assert.equal(cancelCount, 0);
});

import assert from "node:assert/strict";
import test from "node:test";
import { clearManualEditorScheduledWork } from "../dist/workspaces/manual-edit/manualEditorScheduling.js";

test("StrictMode cleanup releases manual editor scheduling refs and allows rescheduling", () => {
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

  // StrictMode reruns effects after cleanup, so new browser tasks must be scheduled and released normally.
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

test("cleanup does not call browser cancellation APIs when no work is scheduled", () => {
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

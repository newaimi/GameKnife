import assert from "node:assert/strict";
import test from "node:test";
import { readJobStatusPresentation } from "../dist/components/jobStatus.js";
import { readModelInstallPresentation } from "../dist/components/modelInstallStatus.js";

test("readJobStatusPresentation maps every backend job state", () => {
  assert.deepEqual(readJobStatusPresentation("pending"), { label: "等待中", tone: "warning", busy: true });
  assert.deepEqual(readJobStatusPresentation("running"), { label: "处理中", tone: "info", busy: true });
  assert.deepEqual(readJobStatusPresentation("success"), { label: "已完成", tone: "success", busy: false });
  assert.deepEqual(readJobStatusPresentation("failed"), { label: "失败", tone: "danger", busy: false });
});

test("readModelInstallPresentation keeps installed and unavailable states distinct", () => {
  assert.equal(readModelInstallPresentation({ status: "success", installed: true, progress: 100, message: "完成" }).installed, true);
  const unavailable = readModelInstallPresentation({ status: "unavailable", progress: 0, message: "服务离线", error: "连接失败" });
  assert.equal(unavailable.label, "服务不可用");
  assert.equal(unavailable.tone, "danger");
  assert.equal(unavailable.installBlocked, true);
});

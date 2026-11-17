import assert from "node:assert/strict";
import test from "node:test";
import { readJobStatusPresentation } from "../dist/components/jobStatus.js";
import { readModelInstallPresentation } from "../dist/components/modelInstallStatus.js";
import { createGameKnifeI18n } from "@gameknife/i18n";

const i18n = await createGameKnifeI18n({ initialLanguage: "en", detectLanguage: false });

test("readJobStatusPresentation maps every backend job state", () => {
  const t = i18n.getFixedT("en", "jobs");
  assert.deepEqual(readJobStatusPresentation("pending", t), { label: "Queued", tone: "warning", busy: true });
  assert.deepEqual(readJobStatusPresentation("running", t), { label: "Processing", tone: "info", busy: true });
  assert.deepEqual(readJobStatusPresentation("success", t), { label: "Completed", tone: "success", busy: false });
  assert.deepEqual(readJobStatusPresentation("failed", t), { label: "Failed", tone: "danger", busy: false });
});

test("readModelInstallPresentation keeps installed and unavailable states distinct", () => {
  const t = i18n.getFixedT("en", "settings");
  assert.equal(readModelInstallPresentation({ status: "success", installed: true, progress: 100, message: "Complete" }, t).installed, true);
  const unavailable = readModelInstallPresentation({ status: "unavailable", progress: 0, message: "Service offline", error: "Connection failed" }, t);
  assert.equal(unavailable.label, "Service unavailable");
  assert.equal(unavailable.tone, "danger");
  assert.equal(unavailable.installBlocked, true);
});

test("readModelInstallPresentation localizes backend status messages at the frontend boundary", () => {
  const t = i18n.getFixedT("zh-CN", "settings");
  const installing = readModelInstallPresentation({ status: "running", progress: 42, message: "Downloading model files." }, t);

  assert.equal(installing.label, t("install.installing"));
  assert.equal(installing.message, t("install.installingMessage"));
  assert.notEqual(installing.message, "Downloading model files.");
});

import commonEn from "./locales/en/common.json" with { type: "json" };
import helpEn from "./locales/en/help.json" with { type: "json" };
import jobsEn from "./locales/en/jobs.json" with { type: "json" };
import manualEditorEn from "./locales/en/manual-editor.json" with { type: "json" };
import settingsEn from "./locales/en/settings.json" with { type: "json" };
import toolsEn from "./locales/en/tools.json" with { type: "json" };
import workbenchEn from "./locales/en/workbench.json" with { type: "json" };
import workflowsEn from "./locales/en/workflows.json" with { type: "json" };
import commonZhCn from "./locales/zh-CN/common.json" with { type: "json" };
import helpZhCn from "./locales/zh-CN/help.json" with { type: "json" };
import jobsZhCn from "./locales/zh-CN/jobs.json" with { type: "json" };
import manualEditorZhCn from "./locales/zh-CN/manual-editor.json" with { type: "json" };
import settingsZhCn from "./locales/zh-CN/settings.json" with { type: "json" };
import toolsZhCn from "./locales/zh-CN/tools.json" with { type: "json" };
import workbenchZhCn from "./locales/zh-CN/workbench.json" with { type: "json" };
import workflowsZhCn from "./locales/zh-CN/workflows.json" with { type: "json" };

export const namespaces = ["common", "help", "jobs", "manualEditor", "settings", "tools", "workbench", "workflows"] as const;

export const resources = {
  en: {
    common: commonEn,
    help: helpEn,
    jobs: jobsEn,
    manualEditor: manualEditorEn,
    tools: toolsEn,
    workbench: workbenchEn,
    settings: settingsEn,
    workflows: workflowsEn,
  },
  "zh-CN": {
    common: commonZhCn,
    help: helpZhCn,
    jobs: jobsZhCn,
    manualEditor: manualEditorZhCn,
    tools: toolsZhCn,
    workbench: workbenchZhCn,
    settings: settingsZhCn,
    workflows: workflowsZhCn,
  },
} as const;

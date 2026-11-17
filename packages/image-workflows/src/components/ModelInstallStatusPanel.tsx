import { Download } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ModelInstallStatus } from "@gameknife/shared-types";
import { Button, FeedbackMessage, ProgressBar, StatusBadge } from "@gameknife/ui-kit";
import { readModelInstallPresentation } from "./modelInstallStatus";

export function ModelInstallStatusPanel({
  label,
  status,
  installDisabled = false,
  onInstall,
}: {
  label: string;
  status: ModelInstallStatus | null;
  installDisabled?: boolean;
  onInstall: () => void | Promise<void>;
}) {
  const { t } = useTranslation("settings");
  const presentation = readModelInstallPresentation(status, t);
  const progressTone = presentation.tone === "danger" ? "danger" : presentation.installed ? "success" : "info";

  return (
    <div className="model-install-status">
      <div className="model-install-status-heading">
        <StatusBadge tone={presentation.tone} busy={presentation.busy}>
          {presentation.label}
        </StatusBadge>
        <strong>{Math.min(100, Math.max(0, Math.round(presentation.progress)))}%</strong>
      </div>
      <ProgressBar value={presentation.progress} label={t("install.progress", { label })} tone={progressTone} />
      <p>{presentation.message}</p>
      {presentation.error ? <FeedbackMessage tone="danger">{presentation.error}</FeedbackMessage> : null}
      {!presentation.installed ? (
        <Button className="install-button" variant="primary" disabled={presentation.installBlocked || installDisabled} onClick={() => void onInstall()}>
          <Download size={18} />
          {t("install.download")}
        </Button>
      ) : null}
    </div>
  );
}

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Download, RadioTower, Wand2 } from "lucide-react";
import { gameKnifeApiClient } from "@gameknife/api-client";
import type { SoundEffectParameters } from "@gameknife/shared-types";
import { NumberField } from "@gameknife/ui-kit";
import { useObjectUrl } from "../../utils/objectUrl";
import { StatusLine } from "../../components/StatusLine";
import { ToolWorkspaceLayout } from "../../components/ToolWorkspaceLayout";
import { WorkbenchActionBar } from "../../components/WorkbenchActionBar";
import { WorkflowFailureDialog } from "../../components/WorkflowFailureDialog";
import { useModelRequirement } from "../../hooks/useModelRequirement";
import { useWorkflowJob } from "../../hooks/useWorkflowJob";
import { useWorkflowWritePermission } from "../../hooks/useWorkflowWritePermission";
import { downloadOutputAsset } from "../../utils/assets";
import { JOB_POLLING_PRESETS, readFirstJobOutputAsset } from "../../utils/jobs";

const DEFAULT_SOUND_EFFECT_PARAMS: SoundEffectParameters = {
  prompt: "",
  duration_seconds: 4,
  seed: null,
  steps: 100,
  cfg_scale: 7,
};

export function SoundEffectWorkspace() {
  const { t } = useTranslation("workflows");
  const [params, setParams] = useState<SoundEffectParameters>(DEFAULT_SOUND_EFFECT_PARAMS);
  const { job, busy, error, setError, failureDialog, setFailureDialog, runJob } = useWorkflowJob();
  const ensureModelReady = useModelRequirement();
  const canWrite = useWorkflowWritePermission("sound-effect");
  const outputAsset = job?.type === "sound_effect_generate" ? readFirstJobOutputAsset(job) : undefined;
  const audioUrl = useObjectUrl(outputAsset?.url ?? "");

  async function run() {
    if (!canWrite) {
      return;
    }
    const prompt = params.prompt.trim();
    if (!prompt) {
      setError(t("sound.promptRequired"));
      return;
    }
    if (!(await ensureModelReady("stable-audio"))) {
      return;
    }
    const parameters = { ...params, prompt };
    await runJob({
      jobType: "sound_effect_generate",
      parameters,
      idempotencyPayload: parameters,
      createJob: (submission) => gameKnifeApiClient.createSoundEffectJob(parameters, submission),
      failureTitle: t("common.jobCreationFailed"),
      failureMessage: t("common.backendRejected", { workflow: t("sound.workflow") }),
      polling: JOB_POLLING_PRESETS.long,
    });
  }

  return (
    <>
      <ToolWorkspaceLayout activeToolId="sound-effect">
        <section className="preview-stage sound-effect-stage">
          <div className="sound-preview-area">
            <div className={`sound-wave ${audioUrl ? "ready" : ""}`} aria-hidden="true">
              {Array.from({ length: 32 }, (_, index) => (
                <span key={index} style={{ ["--bar" as string]: `${28 + ((index * 17) % 58)}%` }} />
              ))}
            </div>
            {audioUrl ? (
              <audio className="sound-audio-player" src={audioUrl} controls />
            ) : (
              <div className="sound-empty">
                <RadioTower size={42} strokeWidth={2.2} />
                <strong>{busy ? t("sound.queued") : t("sound.waiting")}</strong>
              </div>
            )}
          </div>
        </section>

        <aside className="settings-panel sound-effect-settings">
          <h2>{t("sound.parameters")}</h2>
          <label className="number-field">
            <span>{t("sound.prompt")}</span>
            <textarea
              value={params.prompt}
              maxLength={1500}
              placeholder={t("sound.placeholder")}
              onChange={(event) => setParams((current) => ({ ...current, prompt: event.target.value }))}
            />
          </label>
          <label className="number-field">
            <span>{t("sound.duration")}</span>
            <input
              type="number"
              min={0.5}
              max={30}
              step={0.5}
              value={params.duration_seconds}
              onChange={(event) => setParams((current) => ({ ...current, duration_seconds: Number(event.target.value) }))}
            />
          </label>
          <NumberField label={t("sound.steps")} value={params.steps} min={10} max={250} onChange={(steps) => setParams((current) => ({ ...current, steps }))} />
          <label className="number-field">
            <span>{t("sound.guidance")}</span>
            <input
              type="number"
              min={1}
              max={20}
              step={0.5}
              value={params.cfg_scale}
              onChange={(event) => setParams((current) => ({ ...current, cfg_scale: Number(event.target.value) }))}
            />
          </label>
          <label className="number-field">
            <span>{t("sound.seed")}</span>
            <input
              type="number"
              min={-1}
              value={params.seed ?? ""}
              placeholder={t("sound.random")}
              onChange={(event) => setParams((current) => ({ ...current, seed: event.target.value === "" ? null : Number(event.target.value) }))}
            />
          </label>
          <StatusLine error={error} job={job} />
        </aside>

        <WorkbenchActionBar>
          <button className="primary" type="button" disabled={!params.prompt.trim() || busy || !canWrite} onClick={() => void run()}>
            <Wand2 size={17} strokeWidth={2.4} />
            {busy ? t("sound.generating") : t("sound.generate")}
          </button>
          <button className="ghost" type="button" disabled={!outputAsset} onClick={() => (outputAsset ? void downloadOutputAsset(outputAsset, "sound-effect.wav") : undefined)}>
            <Download size={17} strokeWidth={2.4} />
            {t("common.download")}
          </button>
        </WorkbenchActionBar>
      </ToolWorkspaceLayout>

      <WorkflowFailureDialog failureDialog={failureDialog} onCloseFailure={() => setFailureDialog(null)} />
    </>
  );
}

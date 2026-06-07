import { useState } from "react";
import { Download, RadioTower, Wand2 } from "lucide-react";
import { gameKnifeApiClient } from "@gameknife/api-client";
import type { SoundEffectParameters } from "@gameknife/shared-types";
import { NumberField } from "@gameknife/ui-kit";
import { useObjectUrl } from "../../utils/objectUrl";
import { StatusLine } from "../../components/StatusLine";
import { ToolWorkspaceLayout } from "../../components/ToolWorkspaceLayout";
import { WorkflowResultFooter } from "../../components/WorkflowResultFooter";
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
  const [params, setParams] = useState<SoundEffectParameters>(DEFAULT_SOUND_EFFECT_PARAMS);
  const { job, busy, error, setError, failureDialog, setFailureDialog, runJob } = useWorkflowJob();
  const ensureModelReady = useModelRequirement();
  const canWrite = useWorkflowWritePermission("sound-effect");
  const outputAsset = job?.type === "sound_effect_generate" ? readFirstJobOutputAsset(job) : undefined;
  const audioUrl = useObjectUrl(outputAsset?.url ?? "");
  const title = job?.type === "sound_effect_generate" && job.status === "success" ? "声效已生成" : "文字生成声效";
  const summary =
    job?.type === "sound_effect_generate" && job.status === "success"
      ? `${job.result.duration_seconds ?? params.duration_seconds}s · ${job.result.sample_rate ?? "-"} Hz · ${job.result.gpu_device || job.device || "Stable Audio"}`
      : "输入游戏声效提示词后生成 WAV 文件。";

  async function run() {
    if (!canWrite) {
      return;
    }
    const prompt = params.prompt.trim();
    if (!prompt) {
      setError("请输入声效提示词。");
      return;
    }
    if (!(await ensureModelReady("stable-audio"))) {
      return;
    }
    await runJob({
      createJob: () => gameKnifeApiClient.createSoundEffectJob({ ...params, prompt }),
      failureTitle: "任务创建失败",
      failureMessage: "后端拒绝创建声效生成任务，下面是接口返回的错误内容。",
      polling: JOB_POLLING_PRESETS.long,
    });
  }

  return (
    <>
      <ToolWorkspaceLayout activeToolId="sound-effect">
        <section className="preview-stage sound-effect-stage">
          <div className="stage-toolbar">
            <div>
              <h2>{title}</h2>
              <p>{summary}</p>
            </div>
            <div className="toolbar-actions">
              {outputAsset ? (
                <button className="ghost" type="button" onClick={() => void downloadOutputAsset(outputAsset, "sound-effect.wav")}>
                  <Download size={17} strokeWidth={2.4} />
                  下载
                </button>
              ) : null}
              <button className="primary" type="button" disabled={!params.prompt.trim() || busy || !canWrite} onClick={() => void run()}>
                <Wand2 size={17} strokeWidth={2.4} />
                {busy ? "生成中" : "生成声效"}
              </button>
            </div>
          </div>

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
                <strong>{busy ? "声效正在队列中处理" : "等待生成 WAV"}</strong>
                <span>{busy ? "完成后会在这里显示播放器。" : "默认输出可直接用于游戏素材整理。"}</span>
              </div>
            )}
          </div>
        </section>

        <aside className="settings-panel sound-effect-settings">
          <h2>声效参数</h2>
          <label className="number-field">
            <span>提示词</span>
            <textarea
              value={params.prompt}
              maxLength={1500}
              placeholder="例如：short pixel sword slash, crisp impact, no music"
              onChange={(event) => setParams((current) => ({ ...current, prompt: event.target.value }))}
            />
          </label>
          <label className="number-field">
            <span>时长</span>
            <input
              type="number"
              min={0.5}
              max={30}
              step={0.5}
              value={params.duration_seconds}
              onChange={(event) => setParams((current) => ({ ...current, duration_seconds: Number(event.target.value) }))}
            />
          </label>
          <NumberField label="推理步数" value={params.steps} min={10} max={250} onChange={(steps) => setParams((current) => ({ ...current, steps }))} />
          <label className="number-field">
            <span>引导强度</span>
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
            <span>Seed</span>
            <input
              type="number"
              min={-1}
              value={params.seed ?? ""}
              placeholder="随机"
              onChange={(event) => setParams((current) => ({ ...current, seed: event.target.value === "" ? null : Number(event.target.value) }))}
            />
          </label>
          <div className="hint-box">
            <strong>提示词建议</strong>
            <p>用英文描述声源、动作、距离、空间和尾音，结尾加 no music、no voice，短音效建议把时长控制在 1 到 2 秒。</p>
          </div>
          <StatusLine error={error} job={job} />
        </aside>
      </ToolWorkspaceLayout>

      <WorkflowResultFooter refreshKey={job?.id ?? ""} failureDialog={failureDialog} onCloseFailure={() => setFailureDialog(null)} />
    </>
  );
}

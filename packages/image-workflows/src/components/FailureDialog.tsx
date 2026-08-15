import { createPortal } from "react-dom";
import type { JobResponse } from "@gameknife/shared-types";
import { Button } from "@gameknife/ui-kit";
import type { FailureDialogState } from "../types/failure";
import { readJobTitle } from "../utils/jobPresentation";

export function FailureDialog({ dialog, onClose }: { dialog: FailureDialogState; onClose: () => void }) {
  const dialogId = "task-failure-dialog-title";
  const modal = (
    <div className="failure-dialog-backdrop" role="presentation" onClick={onClose}>
      <section className="failure-dialog" role="dialog" aria-modal="true" aria-labelledby={dialogId} onClick={(event) => event.stopPropagation()}>
        <div className="failure-dialog-title">
          <div>
            <span>处理失败</span>
            <strong id={dialogId}>{dialog.title}</strong>
          </div>
          <Button size="small" onClick={onClose}>
            关闭
          </Button>
        </div>
        <p>{dialog.message}</p>
        <pre>{dialog.detail}</pre>
      </section>
    </div>
  );

  // 失败弹窗必须脱离工作台画布的缩放和平移上下文，否则报错内容会跟随预览区一起变形。
  return createPortal(modal, document.body);
}

export function readJobFailureDialog(job: JobResponse): FailureDialogState {
  const detail = job.error_message?.trim() || "后端没有返回具体错误。";
  const jobTitle = readJobTitle(job);
  return {
    title: `${jobTitle}失败`,
    message: job.type === "character_rig_analyze" ? "智能候选拆分没有完成，请根据下面的报错检查模型文件或运行环境。" : "任务没有完成，下面是后端返回的原始错误内容。",
    detail: `任务 ID：${job.id}\n错误内容：${detail}`,
  };
}

export function readRequestFailureDialog(title: string, message: string, error: unknown): FailureDialogState {
  return {
    title,
    message,
    detail: error instanceof Error ? error.message : "请求失败。",
  };
}

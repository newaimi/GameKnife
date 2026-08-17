import { FailureDialog } from "./FailureDialog";
import type { FailureDialogState } from "../types/failure";

interface WorkflowFailureDialogProps {
  /** 当前工作流写入失败时生成的弹窗数据；为空时不占用工作台布局。 */
  failureDialog: FailureDialogState | null;
  /** 用户关闭弹窗后的状态清理入口，由各工作流自行维护失败状态。 */
  onCloseFailure: () => void;
}

/**
 * 统一渲染工作流失败弹窗。任务历史已由独立页面承载，这个组件只保留失败反馈，
 * 避免每个工具重复拼装弹窗，同时不会把任务记录重新带回固定视口工作台。
 */
export function WorkflowFailureDialog({ failureDialog, onCloseFailure }: WorkflowFailureDialogProps) {
  return failureDialog ? <FailureDialog dialog={failureDialog} onClose={onCloseFailure} /> : null;
}

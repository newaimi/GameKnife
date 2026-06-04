import type { ManualEditSource } from "../types/manualEdit";
import { saveManualEditTransfer } from "../workspaces/manual-edit/transfer";

export async function openManualEdit(source: Pick<ManualEditSource, "name" | "url" | "sourceFileId" | "sourceContext">) {
  // 临时图片写入 IndexedDB 是异步操作，必须先在用户点击的同步调用栈里打开新标签页。
  // 否则保存完成后再 window.open，浏览器会把它当成非用户触发弹窗拦截。
  const targetWindow = window.open("", "_blank");
  try {
    const transferId = await saveManualEditTransfer(source);
    const url = new URL("/manual-edit", window.location.origin);
    url.searchParams.set("transfer", transferId);
    if (targetWindow) {
      targetWindow.opener = null;
      targetWindow.location.href = url.toString();
    } else {
      window.open(url.toString(), "_blank", "noopener,noreferrer");
    }
  } catch (error) {
    targetWindow?.close();
    throw error;
  }
}

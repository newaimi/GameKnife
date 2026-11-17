import type { ManualEditSource } from "../types/manualEdit";
import { saveManualEditTransfer } from "../workspaces/manual-edit/transfer";

export async function openManualEdit(source: Pick<ManualEditSource, "name" | "url" | "sourceFileId" | "sourceContext">) {
  // Open the tab synchronously from the click before the asynchronous IndexedDB write. Waiting until the write
  // finishes makes browsers classify window.open as an unsolicited popup.
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

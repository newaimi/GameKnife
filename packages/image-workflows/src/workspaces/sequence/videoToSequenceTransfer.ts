import type { AssetResponse } from "@gameknife/shared-types";

const VIDEO_TO_SEQUENCE_TRANSFER_KEY = "gameknife-video-to-sequence-asset";

export interface VideoToSequenceTransfer {
  asset: AssetResponse;
  action: string;
}

export function saveVideoToSequenceTransfer(transfer: VideoToSequenceTransfer) {
  // Video generation and video-to-frames are independent tools connected by an explicit transfer object.
  // Preserve the selected action so frame extraction does not silently return to its default.
  window.sessionStorage.setItem(VIDEO_TO_SEQUENCE_TRANSFER_KEY, JSON.stringify(transfer));
}

export function consumeVideoToSequenceTransfer(): VideoToSequenceTransfer | null {
  const raw = window.sessionStorage.getItem(VIDEO_TO_SEQUENCE_TRANSFER_KEY);
  if (!raw) {
    return null;
  }
  window.sessionStorage.removeItem(VIDEO_TO_SEQUENCE_TRANSFER_KEY);

  const parsed = JSON.parse(raw) as Partial<VideoToSequenceTransfer>;
  if (!isAssetResponse(parsed.asset)) {
    return null;
  }

  return {
    asset: parsed.asset,
    action: typeof parsed.action === "string" && parsed.action ? parsed.action : "walk_down",
  };
}

function isAssetResponse(value: unknown): value is AssetResponse {
  if (!value || typeof value !== "object") {
    return false;
  }
  const record = value as Partial<AssetResponse>;
  return (
    typeof record.id === "string" &&
    typeof record.filename === "string" &&
    typeof record.mime_type === "string" &&
    typeof record.size_bytes === "number" &&
    typeof record.url === "string"
  );
}

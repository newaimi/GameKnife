import { useCallback, useState, type SetStateAction } from "react";
import type { AssetResponse } from "@gameknife/shared-types";
import { readMessage } from "../utils/errors";

export interface AssetUploadOptions {
  uploadAsset: (file: File) => Promise<AssetResponse>;
  asset?: AssetResponse | null;
  onAssetChange?: (asset: AssetResponse | null) => void;
  onBeforeUpload?: () => void;
  onUploaded?: (asset: AssetResponse) => void;
}

export function useAssetUpload({ uploadAsset, asset: controlledAsset, onAssetChange, onBeforeUpload, onUploaded }: AssetUploadOptions) {
  const [localAsset, setLocalAsset] = useState<AssetResponse | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const asset = controlledAsset === undefined ? localAsset : controlledAsset;
  const setAsset = useCallback(
    (nextAsset: SetStateAction<AssetResponse | null>) => {
      // 上传 Hook 同时服务共享图片素材和独立视频素材。
      // 受控模式只把结果交回上层会话，避免每个工具页各自保存一份过期素材。
      if (controlledAsset === undefined) {
        setLocalAsset(nextAsset);
        return;
      }

      const resolvedAsset = typeof nextAsset === "function" ? nextAsset(controlledAsset) : nextAsset;
      onAssetChange?.(resolvedAsset);
    },
    [controlledAsset, onAssetChange],
  );

  const upload = useCallback(
    async (file: File) => {
      setUploading(true);
      setUploadError("");
      onBeforeUpload?.();
      try {
        const uploaded = await uploadAsset(file);
        setAsset(uploaded);
        onUploaded?.(uploaded);
        return uploaded;
      } catch (exc) {
        setUploadError(readMessage(exc));
        return null;
      } finally {
        setUploading(false);
      }
    },
    [onBeforeUpload, onUploaded, setAsset, uploadAsset],
  );

  const resetAsset = useCallback(() => {
    setAsset(null);
    setUploadError("");
  }, [setAsset]);

  return {
    asset,
    setAsset,
    upload,
    uploading,
    uploadError,
    setUploadError,
    resetAsset,
  };
}

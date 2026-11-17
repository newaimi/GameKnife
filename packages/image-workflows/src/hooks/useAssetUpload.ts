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
      // The upload hook supports shared images and standalone video assets. Controlled mode returns the result to
      // the owning session so individual tools cannot retain stale copies.
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

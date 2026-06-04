import { useCallback, useState } from "react";
import type { AssetResponse } from "@gameknife/shared-types";
import { readMessage } from "../utils/errors";

export interface AssetUploadOptions {
  uploadAsset: (file: File) => Promise<AssetResponse>;
  onBeforeUpload?: () => void;
  onUploaded?: (asset: AssetResponse) => void;
}

export function useAssetUpload({ uploadAsset, onBeforeUpload, onUploaded }: AssetUploadOptions) {
  const [asset, setAsset] = useState<AssetResponse | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");

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
    [onBeforeUpload, onUploaded, uploadAsset],
  );

  const resetAsset = useCallback(() => {
    setAsset(null);
    setUploadError("");
  }, []);

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

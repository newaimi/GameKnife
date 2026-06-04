import { gameKnifeApiClient } from "@gameknife/api-client";
import type { AssetResponse } from "@gameknife/shared-types";
import { useAssetUpload } from "./useAssetUpload";

interface ImageAssetUploadOptions {
  onBeforeUpload?: () => void;
  onUploaded?: (asset: AssetResponse) => void;
}

export function useImageAssetUpload({ onBeforeUpload, onUploaded }: ImageAssetUploadOptions = {}) {
  return useAssetUpload({
    uploadAsset: (file) => gameKnifeApiClient.uploadImage(file),
    onBeforeUpload,
    onUploaded,
  });
}

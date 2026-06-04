import { gameKnifeApiClient } from "@gameknife/api-client";
import type { AssetResponse } from "@gameknife/shared-types";
import { useImageAssetSession } from "../context/ImageAssetSession";
import { useAssetUpload } from "./useAssetUpload";

interface ImageAssetUploadOptions {
  onBeforeUpload?: () => void;
  onUploaded?: (asset: AssetResponse) => void;
}

export function useImageAssetUpload({ onBeforeUpload, onUploaded }: ImageAssetUploadOptions = {}) {
  const imageAssetSession = useImageAssetSession();
  return useAssetUpload({
    uploadAsset: (file) => gameKnifeApiClient.uploadImage(file),
    asset: imageAssetSession?.imageAsset,
    onAssetChange: imageAssetSession?.setImageAsset,
    onBeforeUpload,
    onUploaded: (asset) => {
      imageAssetSession?.setImageAsset(asset);
      onUploaded?.(asset);
    },
  });
}

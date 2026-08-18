import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { AssetResponse } from "@gameknife/shared-types";

type ImageAssetSessionValue = {
  imageAsset: AssetResponse | null;
  setImageAsset: (asset: AssetResponse | null) => void;
};

const ImageAssetSessionContext = createContext<ImageAssetSessionValue | null>(null);

export function ImageAssetSessionProvider({ children }: { children: ReactNode }) {
  const [imageAsset, setImageAsset] = useState<AssetResponse | null>(null);
  // Image workbenches share one imported asset across tools. Keep video and sequence inputs outside this session
  // because their input semantics and lifecycles are independent.
  const value = useMemo(() => ({ imageAsset, setImageAsset }), [imageAsset]);

  return <ImageAssetSessionContext.Provider value={value}>{children}</ImageAssetSessionContext.Provider>;
}

export function useImageAssetSession() {
  return useContext(ImageAssetSessionContext);
}

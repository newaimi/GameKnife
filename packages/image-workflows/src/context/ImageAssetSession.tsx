import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { AssetResponse } from "@gameknife/shared-types";

type ImageAssetSessionValue = {
  imageAsset: AssetResponse | null;
  setImageAsset: (asset: AssetResponse | null) => void;
};

const ImageAssetSessionContext = createContext<ImageAssetSessionValue | null>(null);

export function ImageAssetSessionProvider({ children }: { children: ReactNode }) {
  const [imageAsset, setImageAsset] = useState<AssetResponse | null>(null);
  // 图片类工作台在原工程中共享同一份上传素材，切换工具时不能丢失用户刚导入的角色图或素材板。
  // 这里把共享范围限定为图片素材，不接管视频和序列帧，避免不同输入语义互相污染。
  const value = useMemo(() => ({ imageAsset, setImageAsset }), [imageAsset]);

  return <ImageAssetSessionContext.Provider value={value}>{children}</ImageAssetSessionContext.Provider>;
}

export function useImageAssetSession() {
  return useContext(ImageAssetSessionContext);
}

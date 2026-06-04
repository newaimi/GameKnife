import { useEffect, useState } from "react";
import { gameKnifeApiClient } from "@gameknife/api-client";

export function useObjectUrl(url: string) {
  const [objectUrl, setObjectUrl] = useState("");

  useEffect(() => {
    if (!url) {
      setObjectUrl("");
      return undefined;
    }
    let alive = true;
    let nextUrl = "";
    gameKnifeApiClient
      .requestBlob(url)
      .then((blob) => {
        if (!alive) {
          return;
        }
        nextUrl = URL.createObjectURL(blob);
        setObjectUrl(nextUrl);
      })
      .catch(() => {
        // 用户切换工具或路由后，旧预览请求可能晚于组件卸载返回。
        // 这里和成功分支使用同一份存活标记，避免把已过期的资源状态写回页面。
        if (alive) {
          setObjectUrl("");
        }
      });
    return () => {
      alive = false;
      if (nextUrl) {
        URL.revokeObjectURL(nextUrl);
      }
    };
  }, [url]);

  return objectUrl;
}

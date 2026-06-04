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
      .catch(() => setObjectUrl(""));
    return () => {
      alive = false;
      if (nextUrl) {
        URL.revokeObjectURL(nextUrl);
      }
    };
  }, [url]);

  return objectUrl;
}

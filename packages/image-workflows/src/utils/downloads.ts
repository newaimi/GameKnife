export function downloadBlob(blob: Blob, name: string) {
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = name;
  anchor.rel = "noreferrer";
  // 浏览器下载必须由临时 a 标签触发；下载发起后立刻释放对象地址，避免大图反复导出造成内存占用。
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
}

export function buildImageDownloadName(name: string, blob: Blob) {
  const cleanedName = (name || "manual-edit").replace(/[\\/:*?"<>|]+/g, "_").trim();
  const extension = blob.type === "image/jpeg" ? "jpg" : blob.type === "image/webp" ? "webp" : "png";
  if (new RegExp(`\\.${extension}$`, "i").test(cleanedName)) return cleanedName;
  return `${cleanedName.replace(/\\.[^.]+$/, "") || "manual-edit"}.${extension}`;
}

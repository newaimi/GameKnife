export function downloadBlob(blob: Blob, name: string) {
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = name;
  anchor.rel = "noreferrer";
  // Browser downloads require a temporary anchor. Revoke its object URL after dispatch to avoid retaining large exports.
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

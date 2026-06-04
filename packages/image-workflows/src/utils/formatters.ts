export function formatBbox(value: unknown) {
  return Array.isArray(value) ? value.map((item) => Math.round(Number(item))).join(", ") : "";
}

export function formatImageSize(size?: [number, number]) {
  if (!size) {
    return "-";
  }
  return `${size[0]}×${size[1]}`;
}

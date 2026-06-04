export function readMessage(value: unknown): string {
  return value instanceof Error ? value.message : "请求失败。";
}

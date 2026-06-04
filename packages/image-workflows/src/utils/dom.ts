export function isTypingTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false;
  // 全局快捷键只应该响应工作台操作，不能抢走输入框里的普通按键。
  // 这里集中判断可输入目标，避免不同页面各自维护一份略有差异的键盘守卫。
  return ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable;
}

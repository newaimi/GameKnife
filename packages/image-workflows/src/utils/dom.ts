export function isTypingTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false;
  // Global shortcuts must not intercept normal input. Centralizing editable-target detection keeps every
  // workbench on the same keyboard guard.
  return ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable;
}

/**
 * 手动编辑底部操作栏的输入状态。字段直接来自页面权限、保存流程和编辑历史，
 * 计算层不读取组件状态，便于空文档、只读和保存中的边界分别验证。
 */
export type ManualEditorActionStateInput = {
  hasSource: boolean;
  canWrite: boolean;
  saving: boolean;
  canUndo: boolean;
  canRedo: boolean;
};

/** 手动编辑底部操作栏展示的标签和禁用状态。 */
export type ManualEditorActionState = {
  uploadLabel: "导入图片" | "更换图片";
  uploadDisabled: boolean;
  undoDisabled: boolean;
  redoDisabled: boolean;
  saveLabel: "保存" | "保存中";
  saveDisabled: boolean;
  exportDisabled: boolean;
};

/**
 * 按单项操作的真实依赖计算按钮状态。导入只依赖写入权限，导出只依赖当前文档，
 * 保存同时依赖文档、权限和进行中的请求，避免一项操作借用另一项操作的隐含条件。
 */
export function readManualEditorActionState({
  hasSource,
  canWrite,
  saving,
  canUndo,
  canRedo,
}: ManualEditorActionStateInput): ManualEditorActionState {
  return {
    uploadLabel: hasSource ? "更换图片" : "导入图片",
    uploadDisabled: !canWrite,
    undoDisabled: !canUndo,
    redoDisabled: !canRedo,
    saveLabel: saving ? "保存中" : "保存",
    saveDisabled: !hasSource || saving || !canWrite,
    exportDisabled: !hasSource,
  };
}

export interface EditorSize {
  width: number;
  height: number;
}

export interface EditorLayer {
  id: string;
  name: string;
  visible: boolean;
}

export interface EditorDocument {
  id: string;
  size: EditorSize;
  layers: EditorLayer[];
}

export function createEmptyEditorDocument(id: string, size: EditorSize): EditorDocument {
  // 编辑器核心只维护可序列化状态，页面层负责 Canvas 事件和具体 UI。
  // 这样商用版复用编辑能力时，不需要复制手动编辑器的数据结构。
  return {
    id,
    size,
    layers: [],
  };
}

import { gameKnifeApiClient } from "@gameknife/api-client";
import React, { useEffect, useRef, useState } from "react";
import {
  Brush,
  ChevronDown,
  ChevronUp,
  Eraser,
  Eye,
  EyeOff,
  Lasso,
  MousePointer2,
  Pipette,
  SquareDashedMousePointer,
  Trash2,
  Undo2,
  Wand,
} from "lucide-react";
import type { EditorBrushSettings, EditorExportBackgroundMode, EditorExportOptions, EditorTool, EditorZoomPreviewMode } from "@gameknife/editor-core";
import type { FailureDialogState, ManualEditSource } from "../../types/manualEdit";
import { NumberField } from "@gameknife/ui-kit";
import { WorkbenchPreview } from "@gameknife/ui-kit";
import { buildImageDownloadName, downloadBlob } from "../../utils/downloads";
import { EditorCanvas } from "./EditorCanvas";
import { EDITOR_BRUSH_PRESETS, EDITOR_DEFAULT_BRUSH } from "./constants";
import type { EditorStatus, ManualEditorHandle } from "./types";

const MANUAL_EDIT_BACKGROUND_PRESETS = ["#ffffff", "#f5f7fb", "#d7ecff", "#ff3b30", "#1f6fff"];

export function ManualEditPage({
  source,
  gridVisible,
  fileInput,
  onGridVisibleChange,
  onUpload,
  onFailure,
}: {
  source: ManualEditSource | null;
  gridVisible: boolean;
  fileInput: React.RefObject<HTMLInputElement | null>;
  onGridVisibleChange: React.Dispatch<React.SetStateAction<boolean>>;
  onUpload: (file: File) => void;
  onFailure: React.Dispatch<React.SetStateAction<FailureDialogState | null>>;
}) {
  const editorRef = useRef<ManualEditorHandle | null>(null);
  const skipLayerNameCommitRef = useRef<Set<string>>(new Set());
  const [tool, setTool] = useState<EditorTool>("brush");
  const [brush, setBrush] = useState<EditorBrushSettings>(EDITOR_DEFAULT_BRUSH);
  const [transparentBackgroundVisible, setTransparentBackgroundVisible] = useState(true);
  const [exportBackgroundMode, setExportBackgroundMode] = useState<EditorExportBackgroundMode>("transparent");
  const [exportBackgroundColor, setExportBackgroundColor] = useState("#ffffff");
  const [magicTolerance, setMagicTolerance] = useState(28);
  const [magicAlphaTolerance, setMagicAlphaTolerance] = useState(20);
  const [magicContiguous, setMagicContiguous] = useState(true);
  const [zoomPreviewMode, setZoomPreviewMode] = useState<EditorZoomPreviewMode>("off");
  const [alphaThreshold, setAlphaThreshold] = useState(16);
  const [edgeAmount, setEdgeAmount] = useState(1);
  const [featherRadius, setFeatherRadius] = useState(2);
  const [padding, setPadding] = useState(8);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState("");
  const [layerNameDrafts, setLayerNameDrafts] = useState<Record<string, string>>({});
  const [layerOpacityDrafts, setLayerOpacityDrafts] = useState<Record<string, number>>({});
  const [status, setStatus] = useState<EditorStatus>({
    width: 0,
    height: 0,
    canUndo: false,
    canRedo: false,
    dirty: false,
    hasSelection: false,
    hasFloatingSelection: false,
    sample: "-",
    layers: [],
    history: [],
    snapshots: [],
    activeLayerId: null,
  });

  useEffect(() => {
    setSaveMessage("");
    setTool("brush");
    skipLayerNameCommitRef.current.clear();
    setLayerNameDrafts({});
    setLayerOpacityDrafts({});
  }, [source?.url]);

  useEffect(() => {
    const layerMap = new Map(status.layers.map((layer) => [layer.id, layer]));

    setLayerNameDrafts((current) => {
      let changed = false;
      const next: Record<string, string> = {};
      Object.entries(current).forEach(([layerId, draftName]) => {
        const layer = layerMap.get(layerId);
        if (!layer || layer.name === draftName) {
          changed = true;
          return;
        }
        next[layerId] = draftName;
      });
      return changed ? next : current;
    });

    setLayerOpacityDrafts((current) => {
      let changed = false;
      const next: Record<string, number> = {};
      Object.entries(current).forEach(([layerId, draftOpacity]) => {
        const layer = layerMap.get(layerId);
        if (!layer || layer.opacity === draftOpacity) {
          changed = true;
          return;
        }
        next[layerId] = draftOpacity;
      });
      return changed ? next : current;
    });
  }, [status.layers]);

  function importImage() {
    fileInput.current?.click();
  }

  function readExportOptions(): EditorExportOptions {
    return {
      backgroundMode: exportBackgroundMode,
      backgroundColor: exportBackgroundColor,
    };
  }

  async function downloadEditedImage() {
    if (!source || !editorRef.current) return;
    try {
      const blob = await editorRef.current.exportPngBlob(readExportOptions());
      downloadBlob(blob, buildImageDownloadName(source.name || "manual-edit", blob));
    } catch (error) {
      onFailure({
        title: "图片下载失败",
        message: "手动编辑结果无法导出为 PNG。",
        detail: error instanceof Error ? error.message : "下载失败。",
      });
    }
  }

  async function saveEditedImage() {
    if (!source || !editorRef.current || saving) return;
    setSaving(true);
    setSaveMessage("");
    try {
      const blob = await editorRef.current.exportPngBlob(readExportOptions());
      const filename = buildImageDownloadName(source.name || "manual-edit", blob);
      const file = new File([blob], filename, { type: "image/png" });
      const saved = await gameKnifeApiClient.saveManualEditAsset(file, filename, source.sourceFileId, source.sourceContext);
      editorRef.current?.markSaved();
      setSaveMessage(`已保存：${saved.filename}`);
    } catch (error) {
      onFailure({
        title: "图片保存失败",
        message: "手动编辑结果没有写入资源库。",
        detail: error instanceof Error ? error.message : "保存失败。",
      });
    } finally {
      setSaving(false);
    }
  }

  function commitLayerName(layerId: string, currentName: string) {
    const draftName = layerNameDrafts[layerId];
    if (draftName === undefined) return;

    const nextName = draftName.trim() || "图层";
    if (nextName === currentName) {
      setLayerNameDrafts((current) => {
        const next = { ...current };
        delete next[layerId];
        return next;
      });
      return;
    }

    // 图层名称输入会连续触发 change，如果每个字符都进历史栈，大图编辑会很快卡顿。
    // 这里把输入态留在 React 草稿里，失焦或回车时才提交一次真实编辑历史。
    editorRef.current?.updateLayerName(layerId, nextName);
  }

  function discardLayerNameDraft(layerId: string) {
    setLayerNameDrafts((current) => {
      const next = { ...current };
      delete next[layerId];
      return next;
    });
  }

  function previewLayerOpacity(layerId: string, opacity: number) {
    const nextOpacity = Math.min(Math.max(Math.round(opacity), 0), 100);
    setLayerOpacityDrafts((current) => ({ ...current, [layerId]: nextOpacity }));
    editorRef.current?.previewLayerOpacity(layerId, nextOpacity);
  }

  function commitLayerOpacity(layerId: string) {
    editorRef.current?.commitLayerOpacity(layerId);
    setLayerOpacityDrafts((current) => {
      const next = { ...current };
      delete next[layerId];
      return next;
    });
  }

  const activeToolInfo = readManualEditorToolInfo(tool);
  const showBrushControls = tool === "brush" || tool === "eraser" || tool === "restore";
  const showBrushPresets = showBrushControls;
  const showMagicControls = tool === "magic-wand";
  const showColorPicker = tool === "brush";
  const showHardEraser = tool === "eraser";

  return (
    <main className="manual-editor-page">
      <input
        ref={fileInput}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onUpload(file);
          event.currentTarget.value = "";
        }}
      />

      <section className="manual-editor-shell">
        <aside className="manual-editor-tools" aria-label="编辑工具">
          <h2>工具</h2>
          <div className="manual-editor-tool-list">
            <EditorToolButton tool="pan" activeTool={tool} onSelect={setTool} label="移动画布" shortcut="V" icon={<MousePointer2 size={18} strokeWidth={2.5} />} />
            <EditorToolButton tool="move-selection" activeTool={tool} onSelect={setTool} label="移动选区" shortcut="M" icon={<MousePointer2 size={18} strokeWidth={2.5} />} />
            <EditorToolButton
              tool="rect-selection"
              activeTool={tool}
              onSelect={setTool}
              label="矩形选区"
              shortcut="C"
              icon={<SquareDashedMousePointer size={18} strokeWidth={2.5} />}
            />
            <EditorToolButton tool="lasso-selection" activeTool={tool} onSelect={setTool} label="套索" shortcut="L" icon={<Lasso size={18} strokeWidth={2.5} />} />
            <EditorToolButton tool="magic-wand" activeTool={tool} onSelect={setTool} label="魔棒" shortcut="W" icon={<Wand size={18} strokeWidth={2.5} />} />
            <EditorToolButton tool="brush" activeTool={tool} onSelect={setTool} label="画笔" shortcut="B" icon={<Brush size={18} strokeWidth={2.5} />} />
            <EditorToolButton tool="eraser" activeTool={tool} onSelect={setTool} label="橡皮" shortcut="E" icon={<Eraser size={18} strokeWidth={2.5} />} />
            <EditorToolButton tool="picker" activeTool={tool} onSelect={setTool} label="吸管" shortcut="I" icon={<Pipette size={18} strokeWidth={2.5} />} />
            <EditorToolButton tool="restore" activeTool={tool} onSelect={setTool} label="恢复" shortcut="R" icon={<Undo2 size={18} strokeWidth={2.5} />} />
          </div>
        </aside>

        <section className="manual-editor-stage">
          <div className="manual-editor-commandbar">
            <div className="manual-editor-history-actions">
              <button className="ghost compact" type="button" disabled={!status.canUndo} onClick={() => editorRef.current?.undo()}>
                撤销
              </button>
              <button className="ghost compact" type="button" disabled={!status.canRedo} onClick={() => editorRef.current?.redo()}>
                重做
              </button>
            </div>
            <div className="manual-editor-status">
              <strong>{source?.name ?? "未导入图片"}</strong>
              <span>
                {status.width || "-"}×{status.height || "-"} · {status.dirty ? "未保存" : "已同步"} · {status.sample}
              </span>
            </div>
            <div className="manual-editor-export-actions">
              <button className="ghost compact" type="button" onClick={importImage}>
                导入
              </button>
              <button className="ghost compact" type="button" disabled={!source} onClick={() => void saveEditedImage()}>
                保存
              </button>
              <button className="primary compact" type="button" disabled={!source} onClick={() => void downloadEditedImage()}>
                导出
              </button>
            </div>
          </div>

          <WorkbenchPreview key={source ? `manual-edit-${source.url}` : "manual-edit-empty"} contentMode={source ? "intrinsic" : "fill"}>
            {source ? (
              <EditorCanvas
                ref={editorRef}
                source={source}
                tool={tool}
                brush={brush}
                gridVisible={gridVisible}
                transparentBackgroundVisible={transparentBackgroundVisible}
                exportBackgroundMode={exportBackgroundMode}
                exportBackgroundColor={exportBackgroundColor}
                magicTolerance={magicTolerance}
                magicAlphaTolerance={magicAlphaTolerance}
                magicContiguous={magicContiguous}
                zoomPreviewMode={zoomPreviewMode}
                onBrushChange={setBrush}
                onStatusChange={setStatus}
                onFailure={onFailure}
              />
            ) : (
              <div className="manual-editor-empty">
                <strong>导入一张图片</strong>
                <button className="primary" type="button" onClick={importImage}>
                  选择图片
                </button>
              </div>
            )}
          </WorkbenchPreview>
        </section>

        <aside className="manual-editor-inspector">
          <div className="editor-section editor-tool-context">
            <div className="editor-section-heading">
              <div>
                <span>当前工具</span>
                <strong>{activeToolInfo.label}</strong>
              </div>
              <em>{activeToolInfo.shortcut}</em>
            </div>
            <p className="helper-text">{activeToolInfo.description}</p>

            {showBrushControls ? (
              <>
                <NumberField label="大小" value={brush.size} min={1} max={160} onChange={(size) => setBrush((current) => ({ ...current, size }))} />
                <NumberField label="硬度" value={brush.hardness} min={1} max={100} onChange={(hardness) => setBrush((current) => ({ ...current, hardness }))} />
                <NumberField label={tool === "restore" ? "恢复强度" : "不透明度"} value={brush.opacity} min={1} max={100} onChange={(opacity) => setBrush((current) => ({ ...current, opacity }))} />
              </>
            ) : null}

            {showColorPicker ? (
              <label className="number-field">
                <span>颜色</span>
                <input type="color" value={brush.color} onChange={(event) => setBrush((current) => ({ ...current, color: event.target.value }))} />
              </label>
            ) : null}

            {showHardEraser ? (
              <label className="setting-check">
                <input type="checkbox" checked={brush.hardEraser} onChange={(event) => setBrush((current) => ({ ...current, hardEraser: event.target.checked }))} />
                橡皮硬边
              </label>
            ) : null}

            {showMagicControls ? (
              <>
                <NumberField label="颜色容差" value={magicTolerance} min={0} max={255} onChange={setMagicTolerance} />
                <NumberField label="Alpha 容差" value={magicAlphaTolerance} min={0} max={255} onChange={setMagicAlphaTolerance} />
                <label className="setting-check">
                  <input type="checkbox" checked={magicContiguous} onChange={(event) => setMagicContiguous(event.target.checked)} />
                  只选连续区域
                </label>
              </>
            ) : null}
          </div>

          {showBrushPresets ? (
            <div className="editor-section">
              <div className="editor-section-heading compact">
                <strong>笔刷手感</strong>
              </div>
              <div className="editor-preset-grid">
                {EDITOR_BRUSH_PRESETS.map((preset) => (
                  <button className="ghost compact" type="button" key={preset.id} onClick={() => setBrush({ ...preset.settings, color: brush.color })}>
                    {preset.name}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          <div className="editor-section">
            <div className="editor-section-heading compact">
              <strong>视图</strong>
            </div>
            <div className="editor-toggle-grid">
              <label className="setting-check">
                <input type="checkbox" checked={gridVisible} onChange={(event) => onGridVisibleChange(event.target.checked)} />
                格线
              </label>
              <label className="setting-check">
                <input type="checkbox" checked={transparentBackgroundVisible} onChange={(event) => setTransparentBackgroundVisible(event.target.checked)} />
                透明底色
              </label>
            </div>
            <label className="number-field">
              <span>局部预览</span>
              <select value={zoomPreviewMode} onChange={(event) => setZoomPreviewMode(event.target.value as EditorZoomPreviewMode)}>
                <option value="off">关闭</option>
                <option value="loupe">放大镜</option>
                <option value="panel">固定小窗</option>
                <option value="both">同时显示</option>
              </select>
            </label>
          </div>

          <div className="editor-section">
            <div className="editor-section-heading compact">
              <strong>导出</strong>
            </div>
            <label className="number-field">
              <span>导出背景</span>
              <select value={exportBackgroundMode} onChange={(event) => setExportBackgroundMode(event.target.value as EditorExportBackgroundMode)}>
                <option value="transparent">透明背景</option>
                <option value="color">颜色背景</option>
              </select>
            </label>
            {exportBackgroundMode === "color" ? (
              <label className="number-field">
                <span>背景颜色</span>
                <div className="background-color-field">
                  <input type="color" value={exportBackgroundColor} onChange={(event) => setExportBackgroundColor(event.target.value)} aria-label="选择导出背景颜色" />
                  <span>{exportBackgroundColor.toUpperCase()}</span>
                </div>
                <div className="background-color-presets" aria-label="导出背景颜色预设">
                  {MANUAL_EDIT_BACKGROUND_PRESETS.map((color) => (
                    <button
                      key={color}
                      className={exportBackgroundColor.toLowerCase() === color ? "active" : ""}
                      type="button"
                      style={{ backgroundColor: color }}
                      aria-label={`使用 ${color} 作为导出背景颜色`}
                      onClick={() => setExportBackgroundColor(color)}
                    />
                  ))}
                </div>
              </label>
            ) : null}
            <p className="helper-text">颜色背景只在导出或保存时合成，不会改动当前图层像素。</p>
          </div>

          <div className="editor-section">
            <strong>选区</strong>
            <div className="editor-action-row">
              <button className="ghost compact" type="button" disabled={!status.hasSelection} onClick={() => editorRef.current?.deleteSelection()}>
                删除
              </button>
              <button className="ghost compact" type="button" disabled={!status.hasSelection} onClick={() => void editorRef.current?.copySelection()}>
                复制
              </button>
              <button className="ghost compact" type="button" disabled={!status.hasSelection} onClick={() => void editorRef.current?.cutSelection()}>
                剪切
              </button>
              <button className="ghost compact" type="button" disabled={!source} onClick={() => void editorRef.current?.pasteSelection()}>
                粘贴
              </button>
              <button className="ghost compact" type="button" disabled={!status.hasFloatingSelection} onClick={() => editorRef.current?.commitFloatingSelection()}>
                贴入
              </button>
              <button className="ghost compact" type="button" disabled={!status.hasSelection} onClick={() => editorRef.current?.cropSelection()}>
                裁到选区
              </button>
              <button className="ghost compact" type="button" disabled={!status.hasSelection} onClick={() => editorRef.current?.clearSelection()}>
                清除选区
              </button>
            </div>
          </div>

          <div className="editor-section">
            <strong>图层</strong>
            <div className="editor-action-row">
              <button className="ghost compact" type="button" disabled={!source} onClick={() => editorRef.current?.createLayer()}>
                新建
              </button>
              <button className="ghost compact" type="button" disabled={!status.activeLayerId} onClick={() => editorRef.current?.duplicateLayer()}>
                复制层
              </button>
              <button className="ghost compact" type="button" disabled={!status.activeLayerId} onClick={() => editorRef.current?.mergeLayerDown(status.activeLayerId!)}>
                向下合并
              </button>
              <button className="ghost compact" type="button" disabled={!status.activeLayerId} onClick={() => editorRef.current?.flattenLayers()}>
                扁平
              </button>
            </div>
            <div className="editor-layer-list">
              {status.layers.length ? (
	                status.layers.map((layer) => (
	                  <div className={`editor-layer-row ${layer.active ? "active" : ""}`} key={layer.id}>
	                    <button className="ghost icon-button" type="button" onClick={() => editorRef.current?.toggleLayerVisibility(layer.id)} aria-label={layer.visible ? "隐藏图层" : "显示图层"}>
	                      {layer.visible ? <Eye size={15} /> : <EyeOff size={15} />}
	                    </button>
	                    <input
	                      value={layerNameDrafts[layer.id] ?? layer.name}
	                      onFocus={() => editorRef.current?.setActiveLayer(layer.id)}
	                      onChange={(event) => setLayerNameDrafts((current) => ({ ...current, [layer.id]: event.target.value }))}
	                      onBlur={() => {
	                        if (skipLayerNameCommitRef.current.has(layer.id)) {
	                          skipLayerNameCommitRef.current.delete(layer.id);
	                          return;
	                        }
	                        commitLayerName(layer.id, layer.name);
	                      }}
	                      onKeyDown={(event) => {
	                        if (event.key === "Enter") {
	                          event.preventDefault();
	                          event.currentTarget.blur();
	                        }
	                        if (event.key === "Escape") {
	                          event.preventDefault();
	                          skipLayerNameCommitRef.current.add(layer.id);
	                          discardLayerNameDraft(layer.id);
	                          event.currentTarget.blur();
	                        }
	                      }}
	                    />
	                    <button className="ghost icon-button" type="button" onClick={() => editorRef.current?.moveLayer(layer.id, "up")} aria-label="上移图层">
	                      <ChevronUp size={15} />
	                    </button>
                    <button className="ghost icon-button" type="button" onClick={() => editorRef.current?.moveLayer(layer.id, "down")} aria-label="下移图层">
                      <ChevronDown size={15} />
                    </button>
                    <button className="ghost icon-button" type="button" onClick={() => editorRef.current?.deleteLayer(layer.id)} aria-label="删除图层">
                      <Trash2 size={15} />
                    </button>
	                    <label>
	                      <span>透明度</span>
	                      <input
	                        type="range"
	                        min={0}
	                        max={100}
	                        value={layerOpacityDrafts[layer.id] ?? layer.opacity}
	                        onChange={(event) => previewLayerOpacity(layer.id, Number(event.target.value))}
	                        onPointerUp={() => commitLayerOpacity(layer.id)}
	                        onBlur={() => commitLayerOpacity(layer.id)}
	                      />
	                    </label>
	                  </div>
                ))
              ) : (
                <p className="helper-text">导入图片后显示图层。</p>
              )}
            </div>
          </div>

          <div className="editor-section">
            <strong>历史</strong>
            <div className="editor-action-row">
              <button className="ghost compact" type="button" disabled={!source} onClick={() => editorRef.current?.createSnapshot()}>
                保存快照
              </button>
            </div>
            <div className="editor-history-list">
              {status.history.length ? (
                status.history.map((entry, index) => (
                  <button className="editor-history-row" type="button" key={entry.id} onClick={() => editorRef.current?.jumpToHistory(index)}>
                    <span>{entry.title}</span>
                    <em>{new Date(entry.createdAt).toLocaleTimeString()}</em>
                  </button>
                ))
              ) : (
                <p className="helper-text">暂无编辑记录。</p>
              )}
            </div>
            <div className="editor-history-list compact-list">
              {status.snapshots.map((snapshot) => (
                <button className="editor-history-row" type="button" key={snapshot.id} onClick={() => editorRef.current?.restoreSnapshot(snapshot.id)}>
                  <span>{snapshot.title}</span>
                  <em>快照</em>
                </button>
              ))}
            </div>
          </div>

          <div className="editor-section">
            <strong>修边</strong>
            <NumberField label="Alpha 阈值" value={alphaThreshold} min={0} max={255} onChange={setAlphaThreshold} />
            <NumberField label="边缘像素" value={edgeAmount} min={1} max={8} onChange={setEdgeAmount} />
            <NumberField label="羽化半径" value={featherRadius} min={1} max={8} onChange={setFeatherRadius} />
            <div className="editor-action-row">
              <button className="ghost compact" type="button" onClick={() => editorRef.current?.applyAlphaThreshold(alphaThreshold)}>
                阈值
              </button>
              <button className="ghost compact" type="button" onClick={() => editorRef.current?.removeAlphaNoise()}>
                去噪点
              </button>
              <button className="ghost compact" type="button" onClick={() => editorRef.current?.contractAlpha(edgeAmount)}>
                收缩
              </button>
              <button className="ghost compact" type="button" onClick={() => editorRef.current?.expandAlpha(edgeAmount)}>
                扩张
              </button>
              <button className="ghost compact" type="button" onClick={() => editorRef.current?.featherAlpha(featherRadius)}>
                羽化
              </button>
            </div>
          </div>

          <div className="editor-section">
            <strong>画布</strong>
            <NumberField label="留边" value={padding} min={0} max={256} onChange={setPadding} />
            <div className="editor-action-row">
              <button className="ghost compact" type="button" onClick={() => editorRef.current?.trimTransparent()}>
                裁透明边
              </button>
              <button className="ghost compact" type="button" onClick={() => editorRef.current?.addPadding(padding)}>
                加留边
              </button>
              <button className="ghost compact" type="button" onClick={() => editorRef.current?.flipHorizontal()}>
                水平翻转
              </button>
              <button className="ghost compact" type="button" onClick={() => editorRef.current?.flipVertical()}>
                垂直翻转
              </button>
              <button className="ghost compact" type="button" onClick={() => editorRef.current?.rotateClockwise()}>
                旋转90
              </button>
            </div>
          </div>

          <button className="ghost install-button" type="button" onClick={importImage}>
            导入图片
          </button>
          <button className="ghost install-button" type="button" disabled={!source} onClick={() => void downloadEditedImage()}>
            下载
          </button>
          <button className="primary install-button" type="button" disabled={!source || saving} onClick={() => void saveEditedImage()}>
            {saving ? "保存中" : "保存到资源库"}
          </button>
          {saveMessage ? <p className="helper-text">{saveMessage}</p> : null}
        </aside>
      </section>
    </main>
  );
}

function EditorToolButton({
  tool,
  activeTool,
  label,
  shortcut,
  icon,
  onSelect,
}: {
  tool: EditorTool;
  activeTool: EditorTool;
  label: string;
  shortcut: string;
  icon?: React.ReactNode;
  onSelect: (tool: EditorTool) => void;
}) {
  return (
    <button className={`editor-tool-button ${activeTool === tool ? "active" : ""}`} type="button" data-tool={tool} onClick={() => onSelect(tool)}>
      {icon ? <span className="editor-tool-icon">{icon}</span> : null}
      <span className="editor-tool-title">{label}</span>
      <em>{shortcut}</em>
    </button>
  );
}

function readManualEditorToolInfo(tool: EditorTool) {
  switch (tool) {
    case "pan":
      return { label: "移动画布", shortcut: "V", description: "拖动画布查看细节，适合放大后移动位置。" };
    case "move-selection":
      return { label: "移动选区", shortcut: "M", description: "拖动已有选区或浮动内容，调整后点击“贴入”确认。" };
    case "rect-selection":
      return { label: "矩形选区", shortcut: "C", description: "拖出矩形范围，再执行复制、剪切、删除或裁切。" };
    case "lasso-selection":
      return { label: "套索", shortcut: "L", description: "沿素材边缘拖出自由选区，适合不规则小组件。" };
    case "magic-wand":
      return { label: "魔棒", shortcut: "W", description: "点击相近颜色或透明区域生成选区，容差越高选得越宽。" };
    case "eraser":
      return { label: "橡皮", shortcut: "E", description: "擦除当前图层像素。硬边适合像素图，柔边适合抠图边缘。" };
    case "picker":
      return { label: "吸管", shortcut: "I", description: "点击图片取色，取到的颜色会用于画笔。" };
    case "restore":
      return { label: "恢复", shortcut: "R", description: "从导入时的原图恢复像素，适合修回误擦区域。" };
    case "brush":
    default:
      return { label: "画笔", shortcut: "B", description: "在当前图层绘制颜色。先选颜色，再按需要调整大小和硬度。" };
  }
}

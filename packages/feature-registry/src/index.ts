import type { ComponentType, LazyExoticComponent } from "react";

export type FeatureComponent = ComponentType | LazyExoticComponent<ComponentType>;

export interface FeatureRoute {
  id: string;
  path: string;
  label: string;
  badge: string;
  permission: string;
  component: FeatureComponent;
}

export interface FeatureEntry {
  id: string;
  label: string;
  badge: string;
  route: string;
  permission: string;
  /**
   * 工具入口是否需要保留当前工作台并在新标签页打开。
   * 该字段只描述导航行为，图片等跨标签页数据仍由具体业务入口负责传递。
   */
  openInNewTab?: boolean;
}

export const communityFeatureEntries: FeatureEntry[] = [
  { id: "background-remove", label: "去背景", badge: "AI", route: "/tools/background-remove", permission: "jobs.create" },
  { id: "upscale", label: "图片放大", badge: "SR", route: "/tools/upscale", permission: "jobs.create" },
  { id: "asset-board", label: "素材板", badge: "AI", route: "/tools/asset-board", permission: "jobs.create" },
  { id: "sequence", label: "序列帧", badge: "Game", route: "/tools/sequence", permission: "jobs.create" },
  { id: "video-generate", label: "AI生成视频", badge: "API", route: "/tools/video-generate", permission: "jobs.create" },
  { id: "video-to-sequence", label: "视频转帧", badge: "Local", route: "/tools/video-to-sequence", permission: "jobs.create" },
  { id: "sound-effect", label: "声效生成", badge: "SFX", route: "/tools/sound-effect", permission: "jobs.create" },
  { id: "manual-edit", label: "手动编辑", badge: "Edit", route: "/manual-edit", permission: "jobs.create", openInNewTab: true },
];

export function createFeatureRegistry(routes: FeatureRoute[]): FeatureRoute[] {
  // 注册表只保留工具事实数据和路由元数据，避免 Community 和商用外壳复制工具页面装配逻辑。
  // 图标仍由具体 UI 包维护，注册表不绑定视觉库，商业版接入时可以按自己的外壳替换展示方式。
  return [...routes];
}

import type { ComponentType, LazyExoticComponent } from "react";

export type FeatureComponent = ComponentType | LazyExoticComponent<ComponentType>;

export interface FeatureRoute {
  id: string;
  path: string;
  label: string;
  component: FeatureComponent;
}

export interface FeatureEntry {
  id: string;
  label: string;
  route: string;
}

export function createFeatureRegistry(routes: FeatureRoute[]): FeatureRoute[] {
  // 注册表只保留路由元数据，避免 Community 和商用外壳复制工具页面装配逻辑。
  return [...routes];
}

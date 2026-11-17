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
   * Whether the tool entry preserves the current workbench by opening in a new tab.
   * This field describes navigation only; the initiating workflow still transfers images and other cross-tab data.
   */
  openInNewTab?: boolean;
}

export const communityFeatureEntries: FeatureEntry[] = [
  { id: "background-remove", label: "Background removal", badge: "AI", route: "/tools/background-remove", permission: "jobs.create" },
  { id: "upscale", label: "Image upscaling", badge: "SR", route: "/tools/upscale", permission: "jobs.create" },
  { id: "asset-board", label: "UI Splitting", badge: "AI", route: "/tools/asset-board", permission: "jobs.create" },
  { id: "sequence", label: "Sequence", badge: "Game", route: "/tools/sequence", permission: "jobs.create" },
  { id: "video-to-sequence", label: "Video to frames", badge: "Local", route: "/tools/video-to-sequence", permission: "jobs.create" },
  { id: "sound-effect", label: "Sound generation", badge: "SFX", route: "/tools/sound-effect", permission: "jobs.create" },
  { id: "manual-edit", label: "Manual editing", badge: "Edit", route: "/manual-edit", permission: "jobs.create", openInNewTab: true },
];

export function createFeatureRegistry(routes: FeatureRoute[]): FeatureRoute[] {
  // The registry stores tool facts and route metadata so application shells can reuse one tool-page composition path.
  // Concrete UI packages still own icons, keeping the registry independent of a visual library and replaceable by the caller.
  return [...routes];
}

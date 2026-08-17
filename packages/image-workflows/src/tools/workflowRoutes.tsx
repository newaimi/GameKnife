import { lazy } from "react";
import { createFeatureRegistry, type FeatureRoute } from "@gameknife/feature-registry";
import { communityToolEntries } from "./toolEntries";

const BackgroundRemoveWorkspace = lazy(() => import("../workspaces/background/BackgroundRemoveWorkspace").then((module) => ({ default: module.BackgroundRemoveWorkspace })));
const UpscaleWorkspace = lazy(() => import("../workspaces/upscale/UpscaleWorkspace").then((module) => ({ default: module.UpscaleWorkspace })));
const AssetBoardWorkspace = lazy(() => import("../workspaces/asset-board/AssetBoardWorkspace").then((module) => ({ default: module.AssetBoardWorkspace })));
const SequenceWorkspace = lazy(() => import("../workspaces/sequence/SequenceWorkspace").then((module) => ({ default: module.SequenceWorkspace })));
const VideoGenerateWorkspace = lazy(() => import("../workspaces/video-generate/VideoGenerateWorkspace").then((module) => ({ default: module.VideoGenerateWorkspace })));
const VideoToSequenceWorkspace = lazy(() => import("../workspaces/video-to-sequence/VideoToSequenceWorkspace").then((module) => ({ default: module.VideoToSequenceWorkspace })));
const SoundEffectWorkspace = lazy(() => import("../workspaces/sound-effect/SoundEffectWorkspace").then((module) => ({ default: module.SoundEffectWorkspace })));
const ManualEditWorkspace = lazy(() => import("../workspaces/manual-edit/ManualEditWorkspace").then((module) => ({ default: module.ManualEditWorkspace })));

const workflowComponentById: Record<string, FeatureRoute["component"]> = {
  "background-remove": BackgroundRemoveWorkspace,
  upscale: UpscaleWorkspace,
  "asset-board": AssetBoardWorkspace,
  sequence: SequenceWorkspace,
  "video-generate": VideoGenerateWorkspace,
  "video-to-sequence": VideoToSequenceWorkspace,
  "sound-effect": SoundEffectWorkspace,
  "manual-edit": ManualEditWorkspace,
};

export const communityWorkflowRoutes = createFeatureRegistry(
  communityToolEntries.map((tool) => ({
    id: tool.id,
    path: tool.route,
    label: tool.label,
    badge: tool.badge,
    permission: tool.permission,
    component: workflowComponentById[tool.id],
  })),
);

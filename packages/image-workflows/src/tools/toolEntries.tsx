import type { ReactNode } from "react";
import { AudioLines, Bone, Clapperboard, Film, ImageOff, Layers, Maximize2, Pencil, RefreshCw, Sparkles, UploadCloud } from "lucide-react";

export type ToolEntry = {
  id: string;
  label: string;
  badge: string;
  route: string;
  permission: string;
};

export const communityToolEntries: ToolEntry[] = [
  { id: "background-remove", label: "去背景", badge: "AI", route: "/tools/background-remove", permission: "jobs.create" },
  { id: "upscale", label: "图片放大", badge: "SR", route: "/tools/upscale", permission: "jobs.create" },
  { id: "asset-board", label: "素材板", badge: "AI", route: "/tools/asset-board", permission: "jobs.create" },
  { id: "sequence", label: "序列帧", badge: "Game", route: "/tools/sequence", permission: "jobs.create" },
  { id: "video-generate", label: "AI生成视频", badge: "API", route: "/tools/video-generate", permission: "jobs.create" },
  { id: "video-to-sequence", label: "视频转帧", badge: "Local", route: "/tools/video-to-sequence", permission: "jobs.create" },
  { id: "character-rig", label: "骨骼拆分", badge: "Rig", route: "/tools/character-rig", permission: "jobs.create" },
  { id: "sound-effect", label: "声效生成", badge: "SFX", route: "/tools/sound-effect", permission: "jobs.create" },
  { id: "manual-edit", label: "手动编辑", badge: "Edit", route: "/manual-edit", permission: "jobs.create" },
];

export const toolIconById: Record<string, ReactNode> = {
  "background-remove": <ImageOff size={22} strokeWidth={2.3} />,
  upscale: <Maximize2 size={22} strokeWidth={2.3} />,
  "asset-board": <Layers size={22} strokeWidth={2.3} />,
  sequence: <Film size={22} strokeWidth={2.3} />,
  "video-generate": <Sparkles size={22} strokeWidth={2.3} />,
  "video-to-sequence": <Clapperboard size={22} strokeWidth={2.3} />,
  "character-rig": <Bone size={22} strokeWidth={2.3} />,
  "sound-effect": <AudioLines size={22} strokeWidth={2.3} />,
  "manual-edit": <Pencil size={22} strokeWidth={2.3} />,
  jobs: <RefreshCw size={22} strokeWidth={2.3} />,
  settings: <UploadCloud size={22} strokeWidth={2.3} />,
};

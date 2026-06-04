import type { ReactNode } from "react";
import { AudioLines, Bone, Clapperboard, Film, ImageOff, Layers, Maximize2, Pencil, RefreshCw, Sparkles, UploadCloud } from "lucide-react";
import { communityFeatureEntries } from "@gameknife/feature-registry";

export const communityToolEntries = communityFeatureEntries;

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

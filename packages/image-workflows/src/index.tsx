import { WorkbenchPreview } from "@gameknife/ui-kit";

export const communityToolEntries = [
  { id: "background-remove", label: "去背景", route: "/tools/background-remove" },
  { id: "upscale", label: "图片放大", route: "/tools/upscale" },
  { id: "asset-board", label: "素材板", route: "/tools/asset-board" },
  { id: "sequence", label: "序列帧", route: "/tools/sequence" },
  { id: "video-generate", label: "AI生成视频", route: "/tools/video-generate" },
  { id: "video-to-sequence", label: "视频转帧", route: "/tools/video-to-sequence" },
  { id: "character-rig", label: "骨骼拆分", route: "/tools/character-rig" },
  { id: "sound-effect", label: "声效生成", route: "/tools/sound-effect" },
  { id: "manual-edit", label: "手动编辑", route: "/manual-edit" },
];

export function CommunityToolHome() {
  return (
    <div className="tool-home">
      {communityToolEntries.map((tool) => (
        <a className="tool-entry" href={tool.route} key={tool.id}>
          {tool.label}
        </a>
      ))}
      <WorkbenchPreview />
    </div>
  );
}

import { gameKnifeApiClient } from "@gameknife/api-client";
import type { JobResponse, OutputAssetRef } from "@gameknife/shared-types";
import { downloadBlob } from "./downloads";

export async function downloadOutputAsset(asset: OutputAssetRef, filename: string) {
  const blob = await gameKnifeApiClient.requestBlob(asset.url);
  downloadBlob(blob, filename || asset.id);
}

export async function downloadJobOutputAsset(job: JobResponse, asset: OutputAssetRef) {
  const blob = await gameKnifeApiClient.requestBlob(asset.url);
  downloadBlob(blob, buildJobOutputFileName(job, asset, blob));
}

function buildJobOutputFileName(job: JobResponse, asset: OutputAssetRef, blob: Blob) {
  const extension = blob.type === "image/png" ? "png" : blob.type.includes("zip") ? "zip" : blob.type.includes("audio") || blob.type.includes("wav") ? "wav" : "bin";
  const prefix =
    job.type === "background_remove"
      ? "cutout"
      : job.type === "image_upscale"
        ? "upscale"
        : job.type === "sound_effect_generate"
          ? "sound"
          : job.type.includes("character_rig")
            ? "rig"
            : job.type.includes("sequence")
              ? "sequence"
              : job.type.includes("export")
                ? "components"
                : "component";
  const sourceName = job.input_filename?.replace(/\.[^.]+$/, "") || asset.id;
  return `${sourceName}-${prefix}.${extension}`;
}

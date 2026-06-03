export type PrincipalKind = "anonymous" | "user";

export interface Principal {
  id: string;
  kind: PrincipalKind;
  displayName: string;
}

export type WorkspaceKind = "local" | "project";

export interface Workspace {
  id: string;
  kind: WorkspaceKind;
  name: string;
}

export type Edition = "community" | "commercial";

export interface CapabilitySet {
  edition: Edition;
  features: string[];
}

export interface AppContext {
  principal: Principal;
  workspace: Workspace;
  capabilities: CapabilitySet;
}

export interface AssetResponse {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  url: string;
}

export type JobStatus = "pending" | "running" | "success" | "failed";

export interface JobResponse {
  id: string;
  type: string;
  status: JobStatus;
  input_asset_id: string;
  input_filename?: string | null;
  input_mime_type?: string | null;
  input_size_bytes?: number | null;
  parameters: Record<string, unknown>;
  result: Record<string, unknown>;
  device?: string | null;
  duration_ms: number;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobPageResponse {
  items: JobResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface SequenceFrameResponse {
  id: string;
  sequence_id: string;
  source_asset_id: string;
  processed_asset_id?: string | null;
  frame_index: number;
  original_name: string;
  width: number;
  height: number;
  bbox: number[];
  offset_x: number;
  offset_y: number;
  duration_ms: number;
  enabled: boolean;
  is_generated: boolean;
  source_url: string;
  preview_url: string;
  created_at: string;
  updated_at: string;
}

export interface SequenceResponse {
  id: string;
  name: string;
  fps: number;
  loop: boolean;
  canvas_width: number;
  canvas_height: number;
  anchor_mode: string;
  anchor_x: number;
  anchor_y: number;
  clean_parameters: Record<string, unknown>;
  status: string;
  frame_count: number;
  enabled_frame_count: number;
  frames: SequenceFrameResponse[];
  warnings: string[];
  created_at: string;
  updated_at: string;
}

export interface CharacterPartResponse {
  id: string;
  rig_id: string;
  part_asset_id?: string | null;
  mask_asset_id?: string | null;
  part_url?: string | null;
  mask_url?: string | null;
  name: string;
  semantic_type: string;
  bbox: number[];
  pivot_x: number;
  pivot_y: number;
  parent_id?: string | null;
  z_index: number;
  enabled: boolean;
  needs_completion: boolean;
  created_at: string;
  updated_at: string;
}

export interface CharacterRigResponse {
  id: string;
  name: string;
  source_asset_id: string;
  source_url: string;
  canvas_width: number;
  canvas_height: number;
  export_format: string;
  status: string;
  part_count: number;
  parts: CharacterPartResponse[];
  warnings: string[];
  created_at: string;
  updated_at: string;
}

export interface OutputAssetRef {
  id: string;
  url: string;
}

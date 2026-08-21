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
  kind?: string;
  mime_type: string;
  size_bytes: number;
  storage_state?: string;
  created_by?: string;
  created_at?: string;
  updated_at?: string;
  url: string;
}

export interface AssetActionResponse {
  id: string;
  label: string;
  route: string;
}

export interface AssetRelationResponse {
  direction: "source" | "derived";
  relation_type: string;
  job_id?: string | null;
  asset: AssetResponse;
}

export interface AssetDetailResponse extends AssetResponse {
  relations: AssetRelationResponse[];
  available_actions: AssetActionResponse[];
}

export interface AssetPageResponse {
  items: AssetResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface ComponentCandidate {
  id: number;
  bbox: [number, number, number, number];
  area: number;
  selected: boolean;
  preview_asset_id?: string | null;
  preview_url?: string;
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
  error_code?: string | null;
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
  bbox: [number, number, number, number];
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

export interface SequenceCleanParameters {
  alpha_threshold: number;
  alpha_smoothing: number;
  trim_padding: number;
  canvas_padding: number;
  denoise: boolean;
  reference_frame_id?: string;
  color_match: boolean;
  stabilize: boolean;
  stabilize_strength: number;
}

export interface VideoGenerationConfig {
  provider: "aliyun_dashscope" | "seedance";
  base_url: string;
  api_key_configured: boolean;
  masked_api_key?: string | null;
}

export type VideoSequenceProvider = "aliyun_dashscope" | "seedance";

export interface VideoSequenceGenerateParameters {
  action: string;
  prompt: string;
  negative_prompt: string;
  duration: number;
  resolution: string;
}

export interface VideoToSequenceParameters {
  action: string;
  clip_start_seconds: number;
  clip_end_seconds: number;
  fps: number;
  output_size: 128 | 256 | 512 | number;
  loop: boolean;
  alpha_smoothing: number;
  stabilize: boolean;
}

export interface OutputAssetRef {
  id: string;
  url: string;
}

export type UpscaleStyle = "general" | "anime" | "noisy" | "pixel";

export interface BackgroundRemoveParameters {
  alpha_smoothing: number;
}

export interface AssetBoardParameters {
  alpha_threshold: number;
  min_component_area: number;
  alpha_smoothing: number;
  alpha_contract: number;
  alpha_feather: number;
  alpha_defringe: number;
  export_padding: number;
}

export interface UpscaleParameters {
  style: UpscaleStyle;
  scale: 2 | 4 | 8;
  denoise: number;
  tile_size: number;
}

export interface SoundEffectParameters {
  prompt: string;
  duration_seconds: number;
  seed: number | null;
  steps: number;
  cfg_scale: number;
}

export interface RuntimeSettings {
  edition: Edition;
  workspace_id: string;
  storage: "local_file_storage" | "enterprise_storage";
  system: {
    app_version: string;
    build_number: string;
    git_sha: string;
    build_time: string;
    storage_root: string;
    database_path: string;
    max_upload_mb: number;
    cors_origins: string[];
  };
  runtime: {
    python_version: string;
    platform: string;
    pytorch_available: boolean;
    pytorch_version: string | null;
    cuda_available: boolean;
    cuda_version: string | null;
    cudnn_version: string | null;
    mps_available: boolean;
    gpu_count: number;
    current_gpu_index: number | null;
    current_gpu_name: string | null;
    gpus: Array<{
      index: number;
      name: string;
      total_memory_mb: number | null;
      capability: string | null;
    }>;
    error?: string | null;
  };
  birefnet: {
    model_id: string;
    device: string;
    model_input_size: number;
    gpu_concurrency: number;
    lazy_load: boolean;
    install_status: BiRefNetInstallStatus;
  };
  upscale_models: {
    models: Array<{
      key: "general" | "anime" | "noisy" | string;
      name: string;
      role: string;
      filename: string;
    }>;
    device: string;
    lazy_load: boolean;
    install_status: UpscaleModelInstallStatus;
  };
  stable_audio: {
    model_id: string;
    device: string;
    base_url_configured: boolean;
    lazy_load: boolean;
    install_status: StableAudioInstallStatus;
  };
  video_generation: VideoGenerationConfig;
}

export interface ModelInstallStatus {
  status: "idle" | "running" | "success" | "failed" | "unconfigured" | "unavailable";
  progress?: number;
  message: string;
  installed?: boolean;
  loaded?: boolean;
  error?: string | null;
}

export type BiRefNetInstallStatus = ModelInstallStatus;

export type UpscaleModelInstallStatus = ModelInstallStatus;

export type StableAudioInstallStatus = ModelInstallStatus & {
  model_id?: string;
  model_files_cached?: boolean;
  runtime_dependencies?: {
    available: boolean;
    missing: string[];
  };
  queue_size?: number;
  queued?: number;
  workers?: Array<{
    device: string;
    runtime_device?: string;
    loaded?: boolean;
    busy?: boolean;
    last_error?: string | null;
  }>;
};

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

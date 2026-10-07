/**
 * API service for communicating with the Agent backend
 */

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export interface JobSpec {
  prompt: string;
  neg_prompt?: string;
  ref_image?: string[];
  style_image?: string[];
  ref_video?: string[];
  style_video?: string[];
  sketch_image?: string[];
  mask_image?: string[];
  fps?: number;
  duration_seconds?: number;
  resolution?: string;
  quality_mode?: "draft" | "final";
  camera_text?: string;
  lighting_text?: string;
  background_text?: string;
  must_have?: string[];
  must_not_have?: string[];
}

export interface TaskLog {
  id: string;
  timestamp: string;
  level: "info" | "warning" | "error" | "success";
  message: string;
}

export interface PendingAction {
  type: "clarification" | "permission";
  id: string;
  question?: string;
  questions?: string[];
  permission_type?: "custom_node" | "model_download";
  items?: Array<{
    name: string;
    source: string;
    size?: string;
  }>;
}

export interface AgentStatus {
  job_id: string | null;
  state: string;
  current_task: string;
  progress: number;
  logs: TaskLog[];
  completed_tasks: string[];
}

export interface Artifact {
  id: string;
  type: "image" | "video" | "workflow";
  filename: string;
  url: string;
  created_at: string;
  iteration?: number;
}

/**
 * Submit a new job to the agent
 */
export async function submitJob(jobSpec: JobSpec): Promise<{ job_id: string }> {
  const response = await fetch(`${API_BASE}/jobs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(jobSpec),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: "Unknown error" }));
    throw new Error(error.error || `HTTP ${response.status}`);
  }

  return response.json();
}

/**
 * Upload assets (images/videos) for a job
 */
export async function uploadAsset(file: File, assetType: string): Promise<{ asset_id: string; path: string }> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("asset_type", assetType);

  const response = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: "Unknown error" }));
    throw new Error(error.error || `HTTP ${response.status}`);
  }

  return response.json();
}

/**
 * Get current agent status
 */
export async function getAgentStatus(): Promise<AgentStatus> {
  const response = await fetch(`${API_BASE}/agent/status`);

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  return response.json();
}

/**
 * Get pending action (clarification or permission request)
 */
export async function getPendingAction(): Promise<PendingAction | null> {
  const response = await fetch(`${API_BASE}/agent/pending_action`);

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  const data = await response.json();
  return data.action || null;
}

/**
 * Submit response to pending action
 */
export async function submitResponse(actionId: string, response: string | boolean): Promise<void> {
  const responseData = await fetch(`${API_BASE}/agent/response`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      action_id: actionId,
      response: typeof response === "boolean" ? (response ? "yes" : "no") : response,
    }),
  });

  if (!responseData.ok) {
    const error = await responseData.json().catch(() => ({ error: "Unknown error" }));
    throw new Error(error.error || `HTTP ${responseData.status}`);
  }
}

/**
 * Get artifacts for a job
 */
export async function getArtifacts(jobId: string): Promise<Artifact[]> {
  const response = await fetch(`${API_BASE}/agent/artifacts/${jobId}`);

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  return response.json();
}

/**
 * Get media file URL
 */
export function getMediaUrl(filename: string): string {
  return `${API_BASE}/media/${filename}`;
}

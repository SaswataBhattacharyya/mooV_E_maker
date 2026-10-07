const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export type ArtifactType = "story" | "characters" | "scenes" | "subscenes" | "dialogue" | "image_jobs";

export interface ProjectArtifact {
  type: ArtifactType;
  status: string;
  path: string;
  updated_at?: string | null;
  content: any;
}

export interface ImageCandidate {
  candidate_id: string;
  filename: string;
  relative_path: string;
  status: string;
  seed: number;
  prompt_id: string;
}

export interface ImageBatch {
  batch_id: string;
  job_id: string;
  title: string;
  prompt: string;
  status: string;
  created_at: string;
  selected_candidate_id?: string;
  candidates: ImageCandidate[];
}

export interface ProjectState {
  id: string;
  title: string;
  story_input: string;
  automation_mode: boolean;
  status: string;
  current_stage: string;
  created_at: string;
  updated_at: string;
  runtime: {
    job_id: string | null;
    state: string;
    current_task: string;
    progress: number;
    completed_tasks: string[];
    last_error: string | null;
    automation_active: boolean;
    automation_task_id?: string | null;
    supervisor?: {
      mode?: string;
      waiting_for_user?: boolean;
      current_review?: string | null;
      last_decision?: string | null;
      last_rationale?: string | null;
      actionable_diagnosis?: {
        layer: string;
        stage: string;
        reason: string;
        next_action: string;
      } | null;
      stage_retry_counts?: Record<string, number>;
      image_retry_counts?: Record<string, number>;
      events?: Array<{
        id: string;
        timestamp: string;
        kind: string;
        level: string;
        message: string;
        details?: any;
      }>;
    };
  };
  artifacts: Record<ArtifactType, ProjectArtifact>;
  image_queue: {
    current_index: number;
    batches: ImageBatch[];
    accepted: Array<{
      job_id: string;
      batch_id: string;
      candidate_id: string;
      relative_path: string;
      prompt: string;
      accepted_at: string;
    }>;
  };
  context_layers: {
    artifact_chain: boolean;
    graphify_enabled: boolean;
    graphify_refs: string[];
    optional_supervisor: string;
    supervisor_enabled: boolean;
  };
  logs: Array<{
    id: string;
    timestamp: string;
    level: string;
    message: string;
  }>;
}

export interface ProjectRuntimeStatus {
  project_id: string;
  title: string;
  runtime: {
    job_id: string | null;
    state: string;
    current_task: string;
    progress: number;
    completed_tasks: string[];
    last_error: string | null;
  };
  status: string;
  current_stage: string;
  logs: Array<{
    id: string;
    timestamp: string;
    level: string;
    message: string;
  }>;
  dependencies: {
    ollama: boolean;
    comfyui: boolean;
  };
  supervisor: {
    mode?: string;
    waiting_for_user?: boolean;
    current_review?: string | null;
    last_decision?: string | null;
    last_rationale?: string | null;
    actionable_diagnosis?: {
      layer: string;
      stage: string;
      reason: string;
      next_action: string;
    } | null;
    stage_retry_counts?: Record<string, number>;
    image_retry_counts?: Record<string, number>;
    events?: Array<{
      id: string;
      timestamp: string;
      kind: string;
      level: string;
      message: string;
      details?: any;
    }>;
  };
  artifacts: ProjectState["artifacts"];
  accepted_images: ProjectState["image_queue"]["accepted"];
}

export const CURRENT_PROJECT_KEY = "agentic-art.currentProjectId";
export const INTAKE_DRAFT_KEY = "agentic-art.intakeDraft";
export const SUPERVISOR_PORT = 3009;

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export async function createProject(payload: {
  title: string;
  story_input: string;
  automation_mode: boolean;
}): Promise<ProjectState> {
  const response = await fetch(`${API_BASE}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse<ProjectState>(response);
}

export async function fetchProject(projectId: string): Promise<ProjectState> {
  const response = await fetch(`${API_BASE}/projects/${projectId}`);
  return parseResponse<ProjectState>(response);
}

export async function fetchProjectStatus(projectId: string): Promise<ProjectRuntimeStatus> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/status`);
  return parseResponse<ProjectRuntimeStatus>(response);
}

export async function generateArtifact(projectId: string, artifactType: ArtifactType): Promise<ProjectState> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/artifacts/${artifactType}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  return parseResponse<ProjectState>(response);
}

export async function updateProjectDraft(payload: {
  projectId: string;
  title: string;
  story_input: string;
  automation_mode: boolean;
}): Promise<ProjectState> {
  const response = await fetch(`${API_BASE}/projects/${payload.projectId}/draft`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: payload.title,
      story_input: payload.story_input,
      automation_mode: payload.automation_mode,
    }),
  });
  return parseResponse<ProjectState>(response);
}

export async function saveArtifact(projectId: string, artifactType: ArtifactType, content: any): Promise<ProjectState> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/artifacts/${artifactType}/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  return parseResponse<ProjectState>(response);
}

export async function createImageBatch(projectId: string, count = 4): Promise<ProjectState> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/image-batches/next`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ count }),
  });
  return parseResponse<ProjectState>(response);
}

export async function createMoreImageBatch(projectId: string, batchId: string, count = 4): Promise<ProjectState> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/image-batches/${batchId}/more`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ count }),
  });
  return parseResponse<ProjectState>(response);
}

export async function acceptImageCandidate(
  projectId: string,
  batchId: string,
  candidateId: string
): Promise<ProjectState> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/image-batches/${batchId}/accept`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ candidate_id: candidateId }),
  });
  return parseResponse<ProjectState>(response);
}

export async function pauseProject(projectId: string): Promise<ProjectState> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/stop`, { method: "POST" });
  return parseResponse<ProjectState>(response);
}

export async function continueProject(projectId: string): Promise<ProjectState> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/continue`, { method: "POST" });
  return parseResponse<ProjectState>(response);
}

export async function resetProject(projectId: string): Promise<ProjectState> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/reset`, { method: "POST" });
  return parseResponse<ProjectState>(response);
}

export function getProjectFileUrl(projectId: string, relativePath: string): string {
  return `${API_BASE}/projects/${projectId}/files/${relativePath}`;
}

export function getSupervisorUrl(projectId?: string | null): string {
  if (typeof window === "undefined") {
    return `http://127.0.0.1:${SUPERVISOR_PORT}/`;
  }

  const url = new URL(window.location.href);
  url.port = String(SUPERVISOR_PORT);
  url.pathname = "/";
  url.search = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  url.hash = "";
  return url.toString();
}

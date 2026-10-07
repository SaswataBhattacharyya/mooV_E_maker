const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export interface VoiceOption {
  value: string;
  label: string;
  path: string;
  audio_path: string;
  reference_path: string;
}

export interface AliasState {
  alice?: string | null;
  bob?: string | null;
  narrator?: string | null;
  alias_file: string;
}

export async function fetchVoices(): Promise<{ voices: VoiceOption[]; alias_file: string }> {
  const response = await fetch(`${API_BASE}/tts/voices`);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function fetchAliases(): Promise<AliasState> {
  const response = await fetch(`${API_BASE}/tts/aliases`);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function saveAliases(payload: { alice: string; bob: string; narrator: string }): Promise<any> {
  const response = await fetch(`${API_BASE}/tts/aliases`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export async function saveStory(formData: FormData): Promise<any> {
  const response = await fetch(`${API_BASE}/story/save`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export async function saveTtsAsset(path: "voice" | "reference", formData: FormData): Promise<any> {
  const response = await fetch(`${API_BASE}/tts/assets/${path}`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export async function analyzeSrt(formData: FormData): Promise<any> {
  const response = await fetch(`${API_BASE}/tts/srt/report`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export type DraftStatus =
  | "needs_clarification"
  | "preview_ready"
  | "uploaded"
  | "auth_required"
  | "error";

export interface DraftResponse {
  draft_id: string;
  status: DraftStatus;
  workout?: unknown;
  preview?: string;
  question?: string;
  error?: string;
}

export interface UploadResponse {
  draft_id: string;
  status: DraftStatus;
  workout_id?: number;
  garmin_url: string;
  error?: string;
}

export interface ModelInfo {
  id: string;
  name: string;
  billing_multiplier?: number;
}

export interface ListModelsResponse {
  models: ModelInfo[];
  default?: string;
}

/** A single event emitted by a streaming parse. */
export interface StageEvent {
  stage: string;
  [k: string]: unknown;
}

/** Handler for the live event stream. */
export interface StreamHandlers {
  onDraftId?: (id: string) => void;
  onStage: (evt: StageEvent) => void;
  signal?: AbortSignal;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return (await res.json()) as T;
}

/**
 * Post a JSON body to an SSE endpoint and dispatch parsed events.
 * Returns the final "result" event payload, expected to be a DraftResponse.
 */
async function streamPost(
  url: string,
  body: unknown,
  handlers: StreamHandlers
): Promise<DraftResponse> {
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(body),
    signal: handlers.signal,
  });
  if (!res.ok || !res.body) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let final: DraftResponse | null = null;

  const flushFrame = (frame: string) => {
    // Each frame is one or more "key: value" lines.
    let event = "message";
    let data = "";
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data += line.slice(5).trim();
    }
    if (!data) return;
    let parsed: unknown;
    try {
      parsed = JSON.parse(data);
    } catch {
      return;
    }
    if (event === "stage") {
      handlers.onStage(parsed as StageEvent);
    } else if (event === "draft") {
      const id = (parsed as { draft_id?: string }).draft_id;
      if (id && handlers.onDraftId) handlers.onDraftId(id);
    } else if (event === "result") {
      final = parsed as DraftResponse;
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (value) buf += decoder.decode(value, { stream: true });
    // SSE frames are separated by blank lines.
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      if (frame.trim()) flushFrame(frame);
    }
    if (done) break;
  }
  if (buf.trim()) flushFrame(buf);

  if (!final) {
    throw new Error("Stream ended without a result event");
  }
  return final;
}

export interface SetupStatus {
  copilot_configured: boolean;
  copilot_login?: string | null;
  copilot_error?: string | null;
  garmin_tokens_cached: boolean;
}

export interface WorkoutSummary {
  workout_id?: number;
  name: string;
  description?: string | null;
  sport_type?: string | null;
  estimated_duration_s?: number | null;
  estimated_distance_m?: number | null;
  created_date?: string | null;
  updated_date?: string | null;
}

export interface ListWorkoutsResponse {
  status: "ok" | "auth_required" | "error";
  workouts: WorkoutSummary[];
  error?: string;
}

export interface WorkoutActionResponse {
  status: "ok" | "auth_required" | "error";
  workout_id?: number;
  error?: string;
}

export const api = {
  listModels: () => request<ListModelsResponse>("/api/models"),

  getSetupStatus: () => request<SetupStatus>("/api/setup/status"),

  setCopilotToken: (token: string) =>
    request<SetupStatus>("/api/setup/copilot", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),

  clearCopilotToken: () =>
    request<SetupStatus>("/api/setup/copilot", { method: "DELETE" }),

  createDraft: (description: string, name?: string, model?: string) =>
    request<DraftResponse>("/api/drafts", {
      method: "POST",
      body: JSON.stringify({ description, name: name ?? "", model }),
    }),

  createDraftStream: (
    description: string,
    handlers: StreamHandlers,
    opts?: { name?: string; model?: string }
  ) =>
    streamPost(
      "/api/drafts/stream",
      { description, name: opts?.name ?? "", model: opts?.model },
      handlers
    ),

  reply: (draftId: string, reply: string) =>
    request<DraftResponse>(`/api/drafts/${draftId}/reply`, {
      method: "POST",
      body: JSON.stringify({ reply }),
    }),

  replyStream: (draftId: string, reply: string, handlers: StreamHandlers) =>
    streamPost(`/api/drafts/${draftId}/reply/stream`, { reply }, handlers),

  revise: (draftId: string, feedback: string) =>
    request<DraftResponse>(`/api/drafts/${draftId}/revise`, {
      method: "POST",
      body: JSON.stringify({ feedback }),
    }),

  reviseStream: (
    draftId: string,
    feedback: string,
    handlers: StreamHandlers
  ) =>
    streamPost(
      `/api/drafts/${draftId}/revise/stream`,
      { feedback },
      handlers
    ),

  accept: (
    draftId: string,
    opts?: { name?: string; email?: string; password?: string }
  ) =>
    request<UploadResponse>(`/api/drafts/${draftId}/accept`, {
      method: "POST",
      body: JSON.stringify(opts ?? {}),
    }),

  delete: (draftId: string) =>
    request<{ status: string }>(`/api/drafts/${draftId}`, {
      method: "DELETE",
    }),

  listRecentWorkouts: (opts?: {
    limit?: number;
    email?: string;
    password?: string;
  }) =>
    request<ListWorkoutsResponse>("/api/workouts/list", {
      method: "POST",
      body: JSON.stringify(opts ?? {}),
    }),

  deleteGarminWorkout: (
    workoutId: number,
    opts?: { email?: string; password?: string }
  ) =>
    request<WorkoutActionResponse>(`/api/workouts/${workoutId}/delete`, {
      method: "POST",
      body: JSON.stringify(opts ?? {}),
    }),
};

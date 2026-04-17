import { useEffect, useState } from "react";

import {
  api,
  type DraftResponse,
  type ModelInfo,
  type SetupStatus,
  type StageEvent,
} from "./api";
import { ActivityIndicator } from "./components/ActivityIndicator";
import { ClarificationPrompt } from "./components/ClarificationPrompt";
import {
  CredentialsModal,
  clearStoredCreds,
  loadCreds,
  type StoredCreds,
} from "./components/CredentialsModal";
import { DescriptionForm } from "./components/DescriptionForm";
import {
  FlowLog,
  stageEntryFrom,
  type FlowEntry,
} from "./components/FlowLog";
import { RecentWorkouts } from "./components/RecentWorkouts";
import { RevisionForm } from "./components/RevisionForm";
import { SetupScreen } from "./components/SetupScreen";
import { StatusBanner } from "./components/StatusBanner";
import { WorkoutPreview } from "./components/WorkoutPreview";
import { Button } from "./components/ui/button";

type UiState =
  | { kind: "editing" }
  | { kind: "clarifying"; draftId: string; question: string }
  | { kind: "preview"; draftId: string; preview: string }
  | { kind: "revising"; draftId: string; preview: string }
  | { kind: "success"; workoutId?: number }
  | { kind: "error"; message: string };

type Activity =
  | null
  | "Parsing your workout…"
  | "Thinking about your answer…"
  | "Revising the workout…"
  | "Uploading to Garmin Connect…"
  | "Discarding draft…";

export function App() {
  const [state, setState] = useState<UiState>({ kind: "editing" });
  const [activity, setActivity] = useState<Activity>(null);
  const [description, setDescription] = useState("");
  const [name, setName] = useState("");
  const [authPrompt, setAuthPrompt] = useState<{
    draftId?: string;
    error?: string;
    retry?: (creds: StoredCreds) => Promise<void>;
  } | null>(null);

  const [models, setModels] = useState<ModelInfo[]>([]);
  const [defaultModel, setDefaultModel] = useState<string | undefined>(
    undefined
  );
  const [model, setModel] = useState<string>("");
  const [showFlow, setShowFlow] = useState<boolean>(false);
  const [flow, setFlow] = useState<FlowEntry[]>([]);

  const [setup, setSetup] = useState<SetupStatus | null>(null);
  const [setupError, setSetupError] = useState<string | null>(null);
  const [recentRefreshKey, setRecentRefreshKey] = useState(0);

  const busy = activity !== null;

  useEffect(() => {
    let cancelled = false;
    api
      .getSetupStatus()
      .then((s) => {
        if (!cancelled) setSetup(s);
      })
      .catch((e) => {
        if (!cancelled) setSetupError(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!setup?.copilot_configured) return;
    let cancelled = false;
    api
      .listModels()
      .then((r) => {
        if (cancelled) return;
        setModels(r.models);
        setDefaultModel(r.default);
        if (r.models.length > 0) {
          setModel(r.default ?? r.models[0].id);
        }
      })
      .catch(() => {
        /* model list is best-effort; backend will use its default */
      });
    return () => {
      cancelled = true;
    };
  }, [setup?.copilot_configured]);

  function pushStage(evt: StageEvent) {
    setFlow((prev) => [...prev, stageEntryFrom(evt)]);
  }

  function applyDraft(resp: DraftResponse) {
    if (resp.status === "needs_clarification") {
      setState({
        kind: "clarifying",
        draftId: resp.draft_id,
        question: resp.question || "Please clarify.",
      });
    } else if (resp.status === "preview_ready") {
      const suggested =
        (resp.workout as { name?: string } | undefined)?.name ?? "";
      setName(suggested || "Workout");
      setState({
        kind: "preview",
        draftId: resp.draft_id,
        preview: resp.preview || "",
      });
    } else {
      setState({
        kind: "error",
        message: resp.error || `Unexpected status: ${resp.status}`,
      });
    }
  }

  async function handleSend() {
    if (!description.trim()) return;
    setActivity("Parsing your workout…");
    setFlow([]);
    try {
      const resp = showFlow
        ? await api.createDraftStream(
            description.trim(),
            { onStage: pushStage },
            { model: model || undefined }
          )
        : await api.createDraft(description.trim(), undefined, model || undefined);
      applyDraft(resp);
    } catch (e) {
      setState({ kind: "error", message: String(e) });
    } finally {
      setActivity(null);
    }
  }

  async function handleReply(reply: string) {
    if (state.kind !== "clarifying") return;
    setActivity("Thinking about your answer…");
    if (showFlow) setFlow([]);
    try {
      const resp = showFlow
        ? await api.replyStream(state.draftId, reply, { onStage: pushStage })
        : await api.reply(state.draftId, reply);
      applyDraft(resp);
    } catch (e) {
      setState({ kind: "error", message: String(e) });
    } finally {
      setActivity(null);
    }
  }

  async function handleRevise(feedback: string) {
    if (state.kind !== "revising") return;
    setActivity("Revising the workout…");
    if (showFlow) setFlow([]);
    try {
      const resp = showFlow
        ? await api.reviseStream(state.draftId, feedback, {
            onStage: pushStage,
          })
        : await api.revise(state.draftId, feedback);
      applyDraft(resp);
    } catch (e) {
      setState({ kind: "error", message: String(e) });
    } finally {
      setActivity(null);
    }
  }

  function handleStartRevise() {
    if (state.kind !== "preview") return;
    setState({
      kind: "revising",
      draftId: state.draftId,
      preview: state.preview,
    });
  }

  function handleCancelRevise() {
    if (state.kind !== "revising") return;
    setState({
      kind: "preview",
      draftId: state.draftId,
      preview: state.preview,
    });
  }

  async function uploadWithCreds(
    draftId: string,
    creds?: StoredCreds
  ): Promise<void> {
    setActivity("Uploading to Garmin Connect…");
    try {
      const resp = await api.accept(draftId, {
        name: name.trim() || undefined,
        email: creds?.email,
        password: creds?.password,
      });
      if (resp.status === "uploaded") {
        setState({ kind: "success", workoutId: resp.workout_id });
        setDescription("");
        setName("");
        setAuthPrompt(null);
        setRecentRefreshKey((n) => n + 1);
        return;
      }
      if (resp.status === "auth_required") {
        if (creds) clearStoredCreds();
        setAuthPrompt({ draftId, error: resp.error });
        return;
      }
      setState({ kind: "error", message: resp.error || "Upload failed." });
    } catch (e) {
      setState({ kind: "error", message: String(e) });
    } finally {
      setActivity(null);
    }
  }

  async function handleAccept() {
    if (state.kind !== "preview") return;
    const stored = loadCreds() ?? undefined;
    await uploadWithCreds(state.draftId, stored);
  }

  async function handleCredsSubmit(creds: StoredCreds) {
    if (!authPrompt) return;
    if (authPrompt.retry) {
      const { retry } = authPrompt;
      setAuthPrompt(null);
      await retry(creds);
      return;
    }
    if (authPrompt.draftId) {
      await uploadWithCreds(authPrompt.draftId, creds);
    }
  }

  function handleCredsCancel() {
    setAuthPrompt(null);
  }

  async function handleDiscard() {
    if (
      state.kind === "preview" ||
      state.kind === "clarifying" ||
      state.kind === "revising"
    ) {
      setActivity("Discarding draft…");
      try {
        await api.delete(state.draftId);
      } catch {
        /* best-effort cleanup */
      }
      setActivity(null);
    }
    setName("");
    setFlow([]);
    setState({ kind: "editing" });
  }

  function handleReset() {
    setDescription("");
    setName("");
    setFlow([]);
    setState({ kind: "editing" });
  }

  const showInputForm =
    state.kind === "editing" ||
    state.kind === "error" ||
    state.kind === "success";

  if (setupError) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-4 px-5 py-10">
        <StatusBanner kind="error" title="Couldn't reach the server">
          {setupError}
        </StatusBanner>
      </div>
    );
  }

  if (setup === null) {
    return (
      <div className="mx-auto max-w-2xl px-5 py-10">
        <ActivityIndicator text="Loading…" />
      </div>
    );
  }

  if (!setup.copilot_configured) {
    return <SetupScreen status={setup} onUpdated={setSetup} />;
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 px-5 py-10">
      <header className="mb-2">
        <h1 className="text-2xl font-semibold tracking-tight">
          Text to Garmin
        </h1>
        <p className="text-sm text-muted-foreground">
          Describe a workout in plain English. Review the preview, then upload
          to Garmin Connect.
        </p>
      </header>

      {state.kind === "error" && (
        <StatusBanner kind="error" title="Something went wrong">
          {state.message}
        </StatusBanner>
      )}
      {state.kind === "success" && (
        <StatusBanner kind="success" title="Uploaded to Garmin Connect">
          {state.workoutId ? `Workout id ${state.workoutId}. ` : ""}
          <a
            className="underline underline-offset-4"
            href="https://connect.garmin.com/modern/workouts"
            target="_blank"
            rel="noreferrer"
          >
            View workouts
          </a>
        </StatusBanner>
      )}

      {showInputForm && (
        <>
          <DescriptionForm
            description={description}
            onDescriptionChange={setDescription}
            onSubmit={handleSend}
            busy={busy}
            models={models}
            model={model}
            onModelChange={setModel}
            defaultModel={defaultModel}
            showFlow={showFlow}
            onShowFlowChange={setShowFlow}
          />
          <ActivityIndicator text={activity} />
          {showFlow && <FlowLog entries={flow} />}
          <RecentWorkouts
            refreshKey={recentRefreshKey}
            onAuthRequired={(retry) =>
              setAuthPrompt({
                retry,
                error:
                  "Sign in to Garmin Connect to view your recent workouts.",
              })
            }
          />
        </>
      )}

      {state.kind === "clarifying" && (
        <>
          <ClarificationPrompt
            question={state.question}
            onReply={handleReply}
            busy={busy}
          />
          <ActivityIndicator text={activity} />
          {showFlow && <FlowLog entries={flow} />}
          <div>
            <Button
              variant="secondary"
              onClick={handleDiscard}
              disabled={busy}
            >
              Discard draft
            </Button>
          </div>
        </>
      )}

      {state.kind === "preview" && (
        <>
          <WorkoutPreview
            preview={state.preview}
            name={name}
            onNameChange={setName}
            onAccept={handleAccept}
            onModify={handleStartRevise}
            onDiscard={handleDiscard}
            busy={busy}
          />
          <ActivityIndicator text={activity} />
          {showFlow && <FlowLog entries={flow} />}
        </>
      )}

      {state.kind === "revising" && (
        <>
          <RevisionForm
            currentPreview={state.preview}
            onSubmit={handleRevise}
            onCancel={handleCancelRevise}
            busy={busy}
          />
          <ActivityIndicator text={activity} />
          {showFlow && <FlowLog entries={flow} />}
        </>
      )}

      {(state.kind === "success" || state.kind === "error") && (
        <div>
          <Button variant="secondary" onClick={handleReset}>
            Start over
          </Button>
        </div>
      )}

      <CredentialsModal
        open={authPrompt !== null}
        initialError={authPrompt?.error}
        onSubmit={handleCredsSubmit}
        onCancel={handleCredsCancel}
        busy={busy}
      />
    </div>
  );
}

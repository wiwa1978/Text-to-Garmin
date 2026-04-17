import type { StageEvent } from "@/api";
import { Card, CardContent } from "@/components/ui/card";

export interface FlowEntry {
  at: number;
  stage: string;
  detail?: string;
}

interface Props {
  entries: FlowEntry[];
}

const STAGE_LABELS: Record<string, string> = {
  preparing_prompt: "Preparing prompt",
  sending_prompt: "Sending prompt to LLM",
  received_response: "Received response",
  validating: "Validating JSON",
  validation_failed: "Validation failed — asking LLM to retry",
  clarification_needed: "LLM is asking a clarifying question",
  workout_ready: "Workout ready",
};

export function stageEntryFrom(evt: StageEvent): FlowEntry {
  const detail: string[] = [];
  if (typeof evt.prompt_chars === "number") {
    detail.push(`${evt.prompt_chars} chars`);
  }
  if (typeof evt.attempt === "number") {
    const max = typeof evt.max_attempts === "number" ? evt.max_attempts : "?";
    detail.push(`attempt ${evt.attempt}/${max}`);
  }
  if (typeof evt.error === "string") {
    detail.push(evt.error);
  }
  return {
    at: Date.now(),
    stage: evt.stage,
    detail: detail.length ? detail.join(" · ") : undefined,
  };
}

export function FlowLog({ entries }: Props) {
  if (entries.length === 0) return null;
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">
          LLM flow
        </div>
        <ol className="flex flex-col gap-1 font-mono text-xs">
          {entries.map((e, i) => {
            const label = STAGE_LABELS[e.stage] ?? e.stage;
            const time = new Date(e.at).toLocaleTimeString();
            return (
              <li
                key={i}
                className="flex gap-3 text-muted-foreground"
              >
                <span className="shrink-0 tabular-nums">{time}</span>
                <span className="shrink-0 text-foreground">{label}</span>
                {e.detail && (
                  <span className="truncate">· {e.detail}</span>
                )}
              </li>
            );
          })}
        </ol>
      </CardContent>
    </Card>
  );
}

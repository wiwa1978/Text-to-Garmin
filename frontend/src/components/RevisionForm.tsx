import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

interface Props {
  currentPreview: string;
  onSubmit: (feedback: string) => void;
  onCancel: () => void;
  busy: boolean;
}

function buildRevisionFeedback(original: string, edited: string): string {
  return (
    "I've edited the workout preview directly. Please update the workout " +
    "JSON so it matches this exact structure. Keep the workout name and " +
    "any unspecified fields unchanged.\n\n" +
    "=== Edited preview ===\n" +
    edited.trim() +
    "\n=== End edited preview ===\n\n" +
    "For reference, the previous preview was:\n\n" +
    "=== Previous preview ===\n" +
    original.trim() +
    "\n=== End previous preview ==="
  );
}

export function RevisionForm({
  currentPreview,
  onSubmit,
  onCancel,
  busy,
}: Props) {
  const [edited, setEdited] = useState(currentPreview);
  const changed = edited.trim() !== currentPreview.trim() && edited.trim() !== "";

  return (
    <Card>
      <CardContent className="pt-6">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!changed) return;
            onSubmit(buildRevisionFeedback(currentPreview, edited));
          }}
          className="flex flex-col gap-4"
        >
          <div className="flex flex-col gap-2">
            <Label htmlFor="edited-preview">Edit the preview</Label>
            <Textarea
              id="edited-preview"
              value={edited}
              onChange={(e) => setEdited(e.target.value)}
              className="min-h-[240px] font-mono text-sm"
              autoFocus
            />
            <p className="text-xs text-muted-foreground">
              Make your changes above. When you apply, the LLM will regenerate
              the workout JSON to match.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={busy || !changed}>
              {busy ? "Revising…" : "Apply revision"}
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => setEdited(currentPreview)}
              disabled={busy || !changed}
            >
              Reset
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={onCancel}
              disabled={busy}
            >
              Cancel
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

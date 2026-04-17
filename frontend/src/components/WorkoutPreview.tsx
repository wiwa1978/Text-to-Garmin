import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Check, Pencil, Trash2 } from "lucide-react";

interface Props {
  preview: string;
  name: string;
  onNameChange: (value: string) => void;
  onAccept: () => void;
  onModify: () => void;
  onDiscard: () => void;
  busy: boolean;
}

export function WorkoutPreview({
  preview,
  name,
  onNameChange,
  onAccept,
  onModify,
  onDiscard,
  busy,
}: Props) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="workout-name">Workout name</Label>
            <Input
              id="workout-name"
              value={name}
              onChange={(e) => onNameChange(e.target.value)}
              placeholder="Workout"
              disabled={busy}
            />
          </div>

          <div className="text-xs uppercase tracking-wide text-muted-foreground">
            Preview
          </div>
          <pre className="whitespace-pre-wrap rounded-md border bg-muted/40 p-4 font-mono text-sm">
            {preview}
          </pre>
          <div className="flex flex-wrap gap-2">
            <Button onClick={onAccept} disabled={busy || !name.trim()}>
              <Check className="size-4" />
              {busy ? "Uploading…" : "Accept & Upload"}
            </Button>
            <Button variant="secondary" onClick={onModify} disabled={busy}>
              <Pencil className="size-4" />
              Modify
            </Button>
            <Button variant="ghost" onClick={onDiscard} disabled={busy}>
              <Trash2 className="size-4" />
              Discard draft
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

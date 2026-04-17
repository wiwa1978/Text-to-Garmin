import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

interface Props {
  question: string;
  onReply: (reply: string) => void;
  busy: boolean;
}

export function ClarificationPrompt({ question, onReply, busy }: Props) {
  const [reply, setReply] = useState("");
  return (
    <Card>
      <CardContent className="pt-6">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (reply.trim()) {
              onReply(reply.trim());
              setReply("");
            }
          }}
          className="flex flex-col gap-4"
        >
          <div>
            <div className="text-xs uppercase tracking-wide text-muted-foreground">
              Copilot asks
            </div>
            <div className="mt-1 text-base">{question}</div>
          </div>
          <Input
            value={reply}
            onChange={(e) => setReply(e.target.value)}
            placeholder="Your answer…"
            autoFocus
          />
          <div>
            <Button type="submit" disabled={busy || !reply.trim()}>
              {busy ? "Sending…" : "Reply"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

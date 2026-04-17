import { useState } from "react";

import { api, type SetupStatus } from "../api";
import { Button } from "./ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "./ui/card";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Alert, AlertDescription, AlertTitle } from "./ui/alert";

interface Props {
  status: SetupStatus;
  onUpdated: (next: SetupStatus) => void;
}

export function SetupScreen({ status, onUpdated }: Props) {
  const [token, setToken] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(
    status.copilot_error ?? null
  );

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const next = await api.setCopilotToken(token.trim());
      setToken("");
      onUpdated(next);
    } catch (err) {
      setError(String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4 px-5 py-10">
      <header className="mb-2">
        <h1 className="text-2xl font-semibold tracking-tight">
          Set up Text to Garmin
        </h1>
        <p className="text-sm text-muted-foreground">
          One-time configuration. Your token is stored on the server and used
          only to talk to GitHub Copilot.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>GitHub Copilot access</CardTitle>
          <CardDescription>
            Paste a GitHub <strong>fine-grained</strong> personal access
            token. Classic <code>ghp_…</code> tokens are not supported.
          </CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent className="flex flex-col gap-3">
            {error && (
              <Alert variant="destructive">
                <AlertTitle>Token did not authenticate</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <Alert variant="destructive">
              <AlertTitle>
                Other people will use your PAT if this URL is public
              </AlertTitle>
              <AlertDescription>
                This app has no login. The token you paste here is stored
                on the server and used by <strong>every</strong> visitor
                to this site — their prompts will be sent to GitHub
                Copilot as <em>you</em>, counted against your Copilot
                quota, and attributed to your GitHub account. Only paste
                a token if the URL is private, or you've put an auth
                layer (Entra ID, IP allow-list, …) in front of it.
              </AlertDescription>
            </Alert>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="copilot-token">Personal access token</Label>
              <Input
                id="copilot-token"
                type="password"
                autoComplete="off"
                spellCheck={false}
                placeholder="github_pat_…"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                disabled={submitting}
                required
              />
              <div className="rounded-md border bg-muted/40 p-3 text-xs text-muted-foreground">
                <p className="mb-1">
                  Create one at{" "}
                  <a
                    className="underline underline-offset-4"
                    href="https://github.com/settings/personal-access-tokens/new"
                    target="_blank"
                    rel="noreferrer"
                  >
                    github.com/settings/personal-access-tokens/new
                  </a>{" "}
                  with only these options set:
                </p>
                <ul className="ml-4 list-disc space-y-0.5">
                  <li>
                    <strong>Repository access</strong>:{" "}
                    <em>Public Repositories (read-only)</em> — this app
                    doesn't use repository access, but GitHub requires you
                    to pick something. Keep it as narrow as possible.
                  </li>
                  <li>
                    <strong>Repository permissions</strong>: leave all at{" "}
                    <em>No access</em>.
                  </li>
                  <li>
                    <strong>Account permissions → Copilot Requests</strong>
                    : <em>Read and write</em>. This is the only permission
                    the app actually needs.
                  </li>
                </ul>
              </div>
            </div>
          </CardContent>
          <CardFooter>
            <Button type="submit" disabled={submitting || !token.trim()}>
              {submitting ? "Verifying…" : "Save token"}
            </Button>
          </CardFooter>
        </form>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Garmin Connect</CardTitle>
          <CardDescription>
            {status.garmin_tokens_cached
              ? "Garmin session tokens are cached on the server."
              : "You'll be asked for your Garmin Connect email and password the first time you upload a workout."}
          </CardDescription>
        </CardHeader>
      </Card>
    </div>
  );
}

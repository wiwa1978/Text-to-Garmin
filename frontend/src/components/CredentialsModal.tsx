import { useEffect, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const STORAGE_KEY = "ttg.garmin.creds";

export interface StoredCreds {
  email: string;
  password: string;
}

export function loadCreds(): StoredCreds | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredCreds;
    if (!parsed.email || !parsed.password) return null;
    return parsed;
  } catch {
    return null;
  }
}

function saveCreds(creds: StoredCreds) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(creds));
}

export function clearStoredCreds() {
  localStorage.removeItem(STORAGE_KEY);
}

interface Props {
  open: boolean;
  initialError?: string;
  onSubmit: (creds: StoredCreds) => void;
  onCancel: () => void;
  busy: boolean;
}

export function CredentialsModal({
  open,
  initialError,
  onSubmit,
  onCancel,
  busy,
}: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);

  useEffect(() => {
    if (!open) return;
    const existing = loadCreds();
    if (existing) {
      setEmail(existing.email);
      setPassword(existing.password);
    }
  }, [open]);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !busy) onCancel();
      }}
    >
      <DialogContent>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!email.trim() || !password) return;
            const creds = { email: email.trim(), password };
            if (remember) saveCreds(creds);
            else clearStoredCreds();
            onSubmit(creds);
          }}
          className="flex flex-col gap-4"
        >
          <DialogHeader>
            <DialogTitle>Garmin Connect login</DialogTitle>
            <DialogDescription>
              The server couldn't find cached Garmin tokens. Enter your Garmin
              Connect credentials to upload this workout.
            </DialogDescription>
          </DialogHeader>

          {initialError && (
            <Alert variant="destructive">
              <AlertDescription>{initialError}</AlertDescription>
            </Alert>
          )}

          <div className="flex flex-col gap-2">
            <Label htmlFor="garmin-email">Email</Label>
            <Input
              id="garmin-email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="garmin-password">Password</Label>
            <Input
              id="garmin-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="remember"
              checked={remember}
              onCheckedChange={(v) => setRemember(v === true)}
            />
            <Label htmlFor="remember" className="cursor-pointer">
              Remember on this browser
            </Label>
          </div>

          <p className="text-xs text-muted-foreground">
            Credentials are stored in your browser's localStorage (plaintext)
            and sent only to this app's backend. Uncheck to avoid persisting
            them.
          </p>

          <DialogFooter className="gap-2">
            <Button
              type="button"
              variant="secondary"
              onClick={onCancel}
              disabled={busy}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={busy || !email.trim() || !password}
            >
              {busy ? "Signing in…" : "Sign in & upload"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

import { Alert, AlertDescription, AlertTitle } from "./ui/alert";
import { Button } from "./ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "./ui/card";

interface Props {
  error?: string;
}

export function LoginScreen({ error }: Props) {
  return (
    <div className="mx-auto flex max-w-xl flex-col gap-4 px-5 py-14">
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">Text to Garmin</CardTitle>
          <CardDescription>
            Sign in with your GitHub account to continue.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {error && (
            <Alert variant="destructive">
              <AlertTitle>Access denied</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          <p className="text-sm text-muted-foreground">
            Only GitHub usernames on the owner's allowlist can use this app.
            If you own this deployment, set{" "}
            <code className="font-mono">ALLOWED_GITHUB_USERS</code> in your
            environment.
          </p>
          <Button asChild>
            <a href="/api/auth/login">Sign in with GitHub</a>
          </Button>
          <p className="text-xs text-muted-foreground">
            We only read your public GitHub login. No scopes are requested;
            the app cannot see your repos, emails, or organizations.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { CheckCircle2, Info, XCircle } from "lucide-react";

interface Props {
  kind: "info" | "error" | "success";
  title?: string;
  children: React.ReactNode;
}

const ICONS = {
  info: Info,
  error: XCircle,
  success: CheckCircle2,
};

const VARIANTS = {
  info: "info" as const,
  error: "destructive" as const,
  success: "success" as const,
};

export function StatusBanner({ kind, title, children }: Props) {
  const Icon = ICONS[kind];
  return (
    <Alert variant={VARIANTS[kind]}>
      <Icon className="size-4" />
      {title && <AlertTitle>{title}</AlertTitle>}
      <AlertDescription>{children}</AlertDescription>
    </Alert>
  );
}

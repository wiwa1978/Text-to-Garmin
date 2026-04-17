import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  text: string | null;
  className?: string;
}

export function ActivityIndicator({ text, className }: Props) {
  return (
    <div
      className={cn(
        "flex min-h-6 items-center gap-2 px-1 py-1 text-sm text-muted-foreground",
        className
      )}
      aria-live="polite"
      aria-busy={text !== null}
    >
      {text ? (
        <>
          <Loader2 className="size-4 animate-spin text-primary" />
          <span>{text}</span>
        </>
      ) : (
        <span className="opacity-0">&nbsp;</span>
      )}
    </div>
  );
}

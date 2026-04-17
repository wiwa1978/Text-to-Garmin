import type { ModelInfo } from "@/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Send } from "lucide-react";

interface Props {
  description: string;
  onDescriptionChange: (value: string) => void;
  onSubmit: () => void;
  busy: boolean;

  models: ModelInfo[];
  model: string;
  onModelChange: (id: string) => void;
  defaultModel?: string;

  showFlow: boolean;
  onShowFlowChange: (value: boolean) => void;
}

export function DescriptionForm({
  description,
  onDescriptionChange,
  onSubmit,
  busy,
  models,
  model,
  onModelChange,
  defaultModel,
  showFlow,
  onShowFlowChange,
}: Props) {
  return (
    <Card>
      <CardContent className="pt-6">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (description.trim()) onSubmit();
          }}
          className="flex flex-col gap-4"
        >
          <div className="flex flex-col gap-2">
            <Label htmlFor="desc">Describe your workout</Label>
            <Textarea
              id="desc"
              className="min-h-[120px]"
              value={description}
              onChange={(e) => onDescriptionChange(e.target.value)}
              placeholder='e.g. "W/u, 20min easy, 4x 2min hills @ 10k effort, c/d"'
            />
            <p className="text-xs text-muted-foreground">
              A descriptive name will be generated automatically. You can edit
              it before uploading.
            </p>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:gap-4">
            <div className="flex flex-1 flex-col gap-2">
              <Label htmlFor="model">Model</Label>
              <Select
                value={model || undefined}
                onValueChange={onModelChange}
                disabled={busy || models.length === 0}
              >
                <SelectTrigger id="model">
                  <SelectValue
                    placeholder={
                      models.length === 0 ? "Loading models…" : "Select a model"
                    }
                  />
                </SelectTrigger>
                <SelectContent>
                  {models.map((m) => {
                    const isDefault = defaultModel && m.id === defaultModel;
                    const mult =
                      m.billing_multiplier != null
                        ? ` (${m.billing_multiplier}x)`
                        : "";
                    return (
                      <SelectItem key={m.id} value={m.id}>
                        {m.name}
                        {mult}
                        {isDefault ? " — default" : ""}
                      </SelectItem>
                    );
                  })}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-2 pb-1">
              <Checkbox
                id="show-flow"
                checked={showFlow}
                onCheckedChange={(v) => onShowFlowChange(v === true)}
              />
              <Label htmlFor="show-flow" className="text-sm font-normal">
                Show LLM flow
              </Label>
            </div>
          </div>

          <div>
            <Button type="submit" disabled={busy || !description.trim()}>
              <Send className="size-4" />
              {busy ? "Sending…" : "Send"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

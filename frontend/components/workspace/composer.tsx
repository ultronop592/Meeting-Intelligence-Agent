import { useState } from "react";
import { Upload, WandSparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";

type ComposerProps = {
  onUploadAndProcess: (file: File) => Promise<void>;
  busy: boolean;
};

export function Composer({ onUploadAndProcess, busy }: ComposerProps) {
  const [prompt, setPrompt] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const submit = async () => {
    if (!file || busy) {
      return;
    }
    await onUploadAndProcess(file);
    setPrompt("");
  };

  return (
    <div className="sticky bottom-0 border-t border-border bg-surface p-3 md:p-4">
      <div className="mx-auto max-w-4xl rounded-[12px] border border-border bg-surface-2 p-3">
        <Textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void submit();
            }
          }}
          placeholder="Message Meeting Intelligence Agent..."
          aria-label="Message composer"
          className="min-h-24 resize-none border-none bg-transparent px-2 py-2 text-[15px] shadow-none focus:border-transparent"
        />

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3">
          <div className="flex flex-wrap items-center gap-2">
            <Input
              type="file"
              accept=".mp3,.wav,.m4a,.flac,.aac,.ogg,.webm"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              className="max-w-xs"
              aria-label="Upload meeting audio file"
            />

            <Button variant="ghost" disabled aria-label="Deep analysis is not available yet">
              <WandSparkles className="mr-2 h-4 w-4" />
              Deep analysis
            </Button>
          </div>

          <Button onClick={() => void submit()} disabled={!file || busy} aria-label="Upload and process selected meeting audio">
            <Upload className="mr-2 h-4 w-4" />
            {busy ? "Processing..." : "Upload and process"}
          </Button>
        </div>
      </div>
    </div>
  );
}

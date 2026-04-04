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

  return (
    <div className="border-t border-brand-cream-200 bg-brand-cream-100 p-3 md:p-4">
      <div className="mx-auto max-w-4xl rounded-2xl border border-brand-cream-200 bg-white p-3 shadow-sm">
        <Textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="Message Meeting Intelligence Agent..."
          className="min-h-24 resize-none border-none bg-transparent px-2 py-2 text-[15px] shadow-none focus:ring-0"
        />

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-brand-cream-100 pt-3">
          <div className="flex flex-wrap items-center gap-2">
            <Input
              type="file"
              accept=".mp3,.wav,.m4a,.flac,.aac,.ogg,.webm"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              className="max-w-xs"
            />

            <Button variant="outline" disabled>
              <WandSparkles className="mr-2 h-4 w-4" />
              Deep analysis
            </Button>
          </div>

          <Button
            onClick={async () => {
              if (!file || busy) {
                return;
              }
              await onUploadAndProcess(file);
            }}
            disabled={!file || busy}
          >
            <Upload className="mr-2 h-4 w-4" />
            Upload and process
          </Button>
        </div>
      </div>
    </div>
  );
}

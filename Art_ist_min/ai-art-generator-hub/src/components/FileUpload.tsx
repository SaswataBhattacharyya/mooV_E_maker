import { useCallback } from "react";
import { Upload, X, Image as ImageIcon, Film, FileAudio2, FileText, File as FileIcon } from "lucide-react";

interface FileUploadProps {
  label: string;
  accept: string;
  file: File | null;
  onFileChange: (file: File | null) => void;
  type: "image" | "video" | "audio" | "text" | "file";
  description?: string;
}

const FileUpload = ({ label, accept, file, onFileChange, type, description }: FileUploadProps) => {
  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const droppedFile = e.dataTransfer.files[0];
      if (droppedFile) onFileChange(droppedFile);
    },
    [onFileChange]
  );

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) onFileChange(selected);
  };

  const Icon =
    type === "image"
      ? ImageIcon
      : type === "video"
        ? Film
        : type === "audio"
          ? FileAudio2
          : type === "text"
            ? FileText
            : FileIcon;

  return (
    <div className="space-y-2">
      <label className="text-sm font-medium text-foreground">{label}</label>
      {file ? (
        <div className="relative flex items-center gap-3 rounded-lg border border-border bg-secondary p-3">
          <Icon className="h-5 w-5 shrink-0 text-primary" />
          <span className="truncate text-sm text-secondary-foreground font-mono">
            {file.name}
          </span>
          <button
            type="button"
            onClick={() => onFileChange(null)}
            className="ml-auto shrink-0 rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ) : (
        <div
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          className="group relative flex cursor-pointer flex-col items-center gap-2 rounded-lg border border-dashed border-border bg-secondary/50 p-6 transition-all glow-border-hover hover:border-primary/40 hover:bg-secondary"
        >
          <Upload className="h-6 w-6 text-muted-foreground transition-colors group-hover:text-primary" />
          <p className="text-sm text-muted-foreground">
            Drop or <span className="text-primary font-medium">browse</span>
          </p>
          {description && (
            <p className="text-xs text-muted-foreground/70">{description}</p>
          )}
          <input
            type="file"
            accept={accept}
            onChange={handleChange}
            className="absolute inset-0 cursor-pointer opacity-0"
          />
        </div>
      )}
    </div>
  );
};

export default FileUpload;

/**
 * Convert an image file to PNG format using Canvas API.
 */
export async function convertImageToPng(file: File): Promise<File> {
  if (file.type === "image/png") return file;

  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        reject(new Error("Canvas context unavailable"));
        return;
      }
      ctx.drawImage(img, 0, 0);
      canvas.toBlob(
        (blob) => {
          URL.revokeObjectURL(url);
          if (!blob) {
            reject(new Error("Conversion failed"));
            return;
          }
          const baseName = file.name.replace(/\.[^.]+$/, "");
          resolve(new File([blob], `${baseName}.png`, { type: "image/png" }));
        },
        "image/png"
      );
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Image load failed"));
    };
    img.src = url;
  });
}

/**
 * Validate a video file is mp4 or webm. True client-side
 * transcoding (webm→mp4) requires ffmpeg.wasm which is heavy;
 * we keep the file as-is and let the backend handle conversion.
 */
export function validateVideoFormat(file: File): boolean {
  return ["video/mp4", "video/webm"].includes(file.type);
}

export interface GenerationPayload {
  text_prompt: string;
  reference_image: string | null;
  style_image: string | null;
  reference_video: string | null;
  style_video: string | null;
  reference_video_description: string | null;
  style_video_description: string | null;
  fps: number | null;
  video_duration: number | null;
  camera_angle: string | null;
  lighting_angle: string | null;
}

/**
 * Build a FormData payload with converted assets + JSON metadata.
 */
export async function buildPayload(
  fields: Omit<GenerationPayload, "reference_image" | "style_image" | "reference_video" | "style_video">,
  files: {
    referenceImage: File | null;
    styleImage: File | null;
    referenceVideo: File | null;
    styleVideo: File | null;
  }
): Promise<FormData> {
  const fd = new FormData();

  // Convert images to PNG
  if (files.referenceImage) {
    const converted = await convertImageToPng(files.referenceImage);
    fd.append("reference_image", converted, "ref.png");
  }
  if (files.styleImage) {
    const converted = await convertImageToPng(files.styleImage);
    fd.append("style_image", converted, "style.png");
  }

  // Videos stay as-is (backend handles webm→mp4 if needed)
  if (files.referenceVideo) {
    const ext = files.referenceVideo.type === "video/webm" ? "webm" : "mp4";
    fd.append("reference_video", files.referenceVideo, `ref.${ext}`);
  }
  if (files.styleVideo) {
    const ext = files.styleVideo.type === "video/webm" ? "webm" : "mp4";
    fd.append("style_video", files.styleVideo, `style.${ext}`);
  }

  // JSON metadata
  const json: GenerationPayload = {
    ...fields,
    reference_image: files.referenceImage ? "assets/ref.png" : null,
    style_image: files.styleImage ? "assets/style.png" : null,
    reference_video: files.referenceVideo ? `assets/ref.${files.referenceVideo.type === "video/webm" ? "webm" : "mp4"}` : null,
    style_video: files.styleVideo ? `assets/style.${files.styleVideo.type === "video/webm" ? "webm" : "mp4"}` : null,
  };

  fd.append("metadata", JSON.stringify(json, null, 2));

  return fd;
}

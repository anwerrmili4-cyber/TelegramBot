const MAX_SIDE = 1600;
const QUALITY = 0.85;
const ACCEPTED = ["image/png", "image/jpeg", "image/webp"];

/**
 * Read a receipt screenshot as a JPEG `data:` URL, scaled down so a phone
 * photo fits comfortably under the server's upload limit.
 */
export async function receiptDataUrl(file: File): Promise<string> {
  if (!ACCEPTED.includes(file.type)) {
    throw new Error("Choisis une image PNG, JPEG ou WebP.");
  }
  const bitmap = await createImageBitmap(file).catch(() => {
    throw new Error("Cette image est illisible. Essaie une autre capture.");
  });
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Ton navigateur ne peut pas préparer cette image.");
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  return canvas.toDataURL("image/jpeg", QUALITY);
}

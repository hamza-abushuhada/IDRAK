"use client";
import { api, ApiError, inPageLanguage } from "./api";

// الاستضافة (Vercel) بترفض أي طلب أكبر من 4.5 ميغا قبل ما يوصل للسيرفر، والمتصفح
// كان يعرضها "network". فبنضغط الملف (gzip) وبنبعثه أجزاء، كل جزء أقل من 4 ميغا،
// وبعدين السيرفر بيجمعها ويكمّل الرفع العادي (api/app/routers/data.py: transfers).
const PART_BYTES = 3.5 * 1024 * 1024;
export const MAX_FILE_MB = 200; // نفس حد السيرفر بعد فكّ الضغط (cleaning/io.py: MAX_BYTES)

// xlsx أصلاً ملف مضغوط (zip)، ضغطه مرة ثانية ما بيوفّر إشي.
async function isZip(file: Blob): Promise<boolean> {
  const head = new Uint8Array(await file.slice(0, 4).arrayBuffer());
  return head[0] === 0x50 && head[1] === 0x4b && head[2] === 0x03 && head[3] === 0x04;
}

async function gzip(file: Blob): Promise<Blob | null> {
  if (typeof CompressionStream === "undefined") return null;
  try {
    return await new Response(file.stream().pipeThrough(new CompressionStream("gzip"))).blob();
  } catch {
    return null;
  }
}

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

// انقطاع نت لحظي ما بيخرّب رفع ملف كبير: كل جزء بينعاد لحد 3 مرات.
async function sendPart(id: string, seq: number, part: Blob) {
  for (let attempt = 1; ; attempt++) {
    try {
      return await api(`/data/transfers/${id}/parts/${seq}`, {
        method: "POST", body: part, headers: { "Content-Type": "application/octet-stream" },
      });
    } catch (e) {
      const status = e instanceof ApiError ? e.status : 0;
      if (attempt >= 3 || (status >= 400 && status < 500)) throw e;
      await wait(1000 * attempt);
    }
  }
}

/** Upload a file of any size (up to MAX_FILE_MB): gzipped, in parts, joined on the server. */
export async function sendFile<T>(file: File, opts: { batchId?: string; onProgress?: (percent: number) => void } = {}): Promise<T> {
  if (file.size > MAX_FILE_MB * 1024 * 1024) {
    throw new ApiError(413, inPageLanguage({
      en: `This file is larger than ${MAX_FILE_MB} MB.`,
      ar: `الملف أكبر من ${MAX_FILE_MB} ميغا.`,
    }));
  }
  const body: Blob = (await isZip(file)) ? file : (await gzip(file)) ?? file;
  const parts = Math.max(1, Math.ceil(body.size / PART_BYTES));
  const id = crypto.randomUUID();
  for (let i = 0; i < parts; i++) {
    opts.onProgress?.(Math.round((i / parts) * 100));
    await sendPart(id, i, body.slice(i * PART_BYTES, (i + 1) * PART_BYTES));
  }
  opts.onProgress?.(100);
  return api<T>(`/data/transfers/${id}/finish`, {
    method: "POST", json: { file_name: file.name, parts, batch_id: opts.batchId ?? null },
  });
}

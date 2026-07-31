import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import { getDataRoot } from "@/lib/dataRoot";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path: segments } = await params;
  const relPath = segments.join("/");
  const root = getDataRoot();
  const absPath = path.join(root, relPath);

  if (!absPath.startsWith(root)) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  if (!fs.existsSync(absPath)) {
    return new NextResponse(`Not found: ${relPath}`, { status: 404 });
  }

  const ext = path.extname(absPath).toLowerCase();
  const mimeMap: Record<string, string> = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
  };

  const buffer = fs.readFileSync(absPath);
  return new NextResponse(buffer, {
    headers: {
      "Content-Type": mimeMap[ext] || "application/octet-stream",
      "Cache-Control": "public, max-age=31536000, immutable",
    },
  });
}

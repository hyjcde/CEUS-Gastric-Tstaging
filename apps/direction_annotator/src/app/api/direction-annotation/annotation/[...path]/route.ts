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

  const raw = fs.readFileSync(absPath, "utf-8");
  return NextResponse.json(JSON.parse(raw));
}

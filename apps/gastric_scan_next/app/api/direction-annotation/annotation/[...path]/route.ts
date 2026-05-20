import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import { resolveConfiguredPaths } from "@/lib/direction-annotation/dataRoot";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path: segments } = await params;
  const relPath = segments.map((segment) => decodeURIComponent(segment)).join("/");
  const { projectRoot } = resolveConfiguredPaths();
  const root = path.resolve(projectRoot);
  const absPath = path.resolve(root, relPath);

  if (absPath !== root && !absPath.startsWith(`${root}${path.sep}`)) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  if (!fs.existsSync(absPath)) {
    return new NextResponse(`Not found: ${relPath}`, { status: 404 });
  }

  const raw = fs.readFileSync(absPath, "utf-8");
  return NextResponse.json(JSON.parse(raw));
}

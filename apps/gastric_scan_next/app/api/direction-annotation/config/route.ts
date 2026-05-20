import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import { getDataRoot, getBatchFilePath, resolveConfiguredPaths } from "@/lib/direction-annotation/dataRoot";

export const dynamic = "force-dynamic";

export async function GET() {
  const root = getDataRoot();
  const resolved = resolveConfiguredPaths(root);
  const batchExists = fs.existsSync(getBatchFilePath());
  return NextResponse.json({
    data_root: root,
    project_root: resolved.projectRoot,
    dataset_dir: resolved.datasetDir,
    batch_exists: batchExists,
  });
}

export async function POST(request: NextRequest) {
  try {
    const { data_root } = await request.json();
    if (!data_root || !fs.existsSync(data_root)) {
      return NextResponse.json({ success: false, error: "目录不存在" }, { status: 400 });
    }
    process.env.DATA_ROOT = data_root;
    return NextResponse.json({ success: true, data_root });
  } catch (err) {
    return NextResponse.json({ success: false, error: String(err) }, { status: 500 });
  }
}

import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import { getSaveDir } from "@/lib/dataRoot";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const payload = await request.json();

    if (!payload.image_path || !payload.patient_id) {
      return NextResponse.json(
        { success: false, error: "Missing image_path or patient_id" },
        { status: 400 }
      );
    }

    const safeName = payload.image_path
      .replace(/[/\\]/g, "__")
      .replace(/\.(jpg|png)$/i, "");
    const fileName = `${safeName}_direction.json`;
    const saveDir = getSaveDir();
    const filePath = path.join(saveDir, fileName);

    if (!payload.timestamp) {
      payload.timestamp = new Date().toISOString();
    }

    fs.mkdirSync(saveDir, { recursive: true });
    fs.writeFileSync(filePath, JSON.stringify(payload, null, 2), "utf-8");

    return NextResponse.json({ success: true, saved_path: filePath });
  } catch (err) {
    return NextResponse.json({ success: false, error: String(err) }, { status: 500 });
  }
}

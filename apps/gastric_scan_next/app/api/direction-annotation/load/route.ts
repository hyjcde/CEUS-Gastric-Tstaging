import { NextRequest, NextResponse } from "next/server";
import { readDirectionAnnotationIfExists } from "@/lib/direction-annotation/dataRoot";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const imagePath = request.nextUrl.searchParams.get("image_path");
  if (!imagePath) {
    return NextResponse.json(
      { success: false, error: "image_path is required" },
      { status: 400 },
    );
  }

  const payload = readDirectionAnnotationIfExists(imagePath);
  if (!payload) {
    return NextResponse.json({ success: true, payload: null });
  }

  return NextResponse.json({ success: true, payload });
}

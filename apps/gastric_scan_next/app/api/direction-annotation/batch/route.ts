import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import { getBatchFilePath, getSaveDir, resolveConfiguredPaths } from "@/lib/direction-annotation/dataRoot";
import { enrichBatchItemWithMask } from "@/lib/direction-annotation/enrich-batch-item";
import type { DirectionBatch, DirectionBatchItem } from "@/lib/direction-annotation/directionAnnotationTypes";

export const dynamic = "force-dynamic";

let cachedBatch: DirectionBatch | null = null;
let cachedPath: string = "";
let cachedMtime: number = 0;

function loadBatch(): DirectionBatch {
  const batchFile = getBatchFilePath();
  const stat = fs.statSync(batchFile);
  const currentBatch = cachedBatch;
  if (currentBatch && cachedPath === batchFile && stat.mtimeMs === cachedMtime) return currentBatch;
  const raw = fs.readFileSync(batchFile, "utf-8");
  const parsedBatch = JSON.parse(raw) as DirectionBatch;
  cachedBatch = parsedBatch;
  cachedPath = batchFile;
  cachedMtime = stat.mtimeMs;
  return parsedBatch;
}

export async function GET(request: NextRequest) {
  const batchFile = getBatchFilePath();
  if (!fs.existsSync(batchFile)) {
    return NextResponse.json(
      { success: false, error: "未找到 direction_annotation_batch.json，请确认数据集目录正确。" },
      { status: 404 }
    );
  }

  try {
    const batch = loadBatch();
    const url = request.nextUrl;
    const page = Math.max(1, parseInt(url.searchParams.get("page") || "1"));
    const pageSize = Math.min(500, Math.max(10, parseInt(url.searchParams.get("pageSize") || "200")));
    const filter = url.searchParams.get("filter") || "all";
    const search = (url.searchParams.get("search") || "").trim().toLowerCase();
    const annotatedFilter = url.searchParams.get("annotated") || "all";

    const saveDir = getSaveDir();
    const savedSet = new Set<string>();
    if (fs.existsSync(saveDir)) {
      for (const file of fs.readdirSync(saveDir)) {
        if (file.endsWith(".json")) {
          try {
            const content = JSON.parse(fs.readFileSync(path.join(saveDir, file), "utf-8"));
            if (content.image_path) savedSet.add(content.image_path);
          } catch {}
        }
      }
    }

    let items: DirectionBatchItem[] = batch.items.map((item) => ({
      ...item,
      is_annotated: savedSet.has(item.image_path),
    }));

    if (filter !== "all") {
      items = items.filter((it) => it.T_stage === filter);
    }
    if (search) {
      items = items.filter((it) =>
        it.patient_id?.toLowerCase().includes(search) ||
        it.image_path?.toLowerCase().includes(search)
      );
    }
    if (annotatedFilter === "yes") {
      items = items.filter((it) => it.is_annotated);
    } else if (annotatedFilter === "no") {
      items = items.filter((it) => !it.is_annotated);
    }

    const totalFiltered = items.length;
    const totalPages = Math.ceil(totalFiltered / pageSize);
    const start = (page - 1) * pageSize;
    const { projectRoot } = resolveConfiguredPaths();
    const pageItems = items.slice(start, start + pageSize).map((item) =>
      enrichBatchItemWithMask(projectRoot, item),
    );

    const patientGroups: Record<string, number[]> = {};
    for (let i = 0; i < pageItems.length; i++) {
      const pid = pageItems[i].patient_id;
      if (!patientGroups[pid]) patientGroups[pid] = [];
      patientGroups[pid].push(i);
    }

    const stageCounts: Record<string, number> = {};
    for (const it of batch.items) {
      const stage = it.T_stage || "unknown";
      stageCounts[stage] = (stageCounts[stage] || 0) + 1;
    }

    return NextResponse.json({
      success: true,
      items: pageItems,
      patient_groups: patientGroups,
      pagination: { page, pageSize, totalFiltered, totalPages, totalAll: batch.items.length },
      stage_counts: stageCounts,
      annotated_count: savedSet.size,
      batch_name: batch.batch_name,
    });
  } catch (err) {
    return NextResponse.json({ success: false, error: String(err) }, { status: 500 });
  }
}

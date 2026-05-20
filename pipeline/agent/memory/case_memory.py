#!/usr/bin/env python3
"""
Build the case memory FAISS index from training set patients.

For each patient in the training CSV:
  1. Load CaseCard (for clinical info and frame paths)
  2. Run classification on each frame → average probabilities
  3. Run morphology on each frame → average features
  4. Extract clinical features
  5. Concatenate into 17-dim vector
  6. Build FAISS IndexFlatL2 + metadata JSON

Usage:
  CUDA_VISIBLE_DEVICES=0 python pipeline/agent/memory/case_memory.py

  # Custom paths
  python pipeline/agent/memory/case_memory.py \\
    --csv pipeline/data/tstaging_4class/train.csv \\
    --output pipeline/agent/memory/index/
"""

import argparse
import json
import logging
from datetime import datetime, timezone
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.core.repo_paths import PROJECT_ROOT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agent.case_memory")

def main():
    parser = argparse.ArgumentParser(description="Build case memory index")
    parser.add_argument("--csv", type=str,
                        default="pipeline/data/tstaging_4class_lumen_lesion_features/train.csv")
    parser.add_argument("--output", type=str,
                        default="pipeline/agent/memory/index/")
    parser.add_argument("--gpu", type=str, default="0")
    parser.add_argument("--batch-frames", type=int, default=2,
                        help="Max frames per patient to process")
    args = parser.parse_args()

    import os
    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu

    import torch
    from agent.core.case_card import load_case_cards_from_csv
    from agent.tools.segmentation_tool import SegmentationTool
    from agent.tools.classification_tool import ClassificationTool
    from agent.tools.morphology_tool import MorphologyTool
    from agent.tools.wall_evidence_tool import WallEvidenceTool
    from agent.memory.feature_extractor import (
        extract_patient_vector, build_key_features_summary, VECTOR_DIM)
    from agent.memory.multimodal_case_vector import VECTOR_DIM as EXT_VECTOR_DIM
    from agent.memory.faiss_index import CaseIndex

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    csv_path = PROJECT_ROOT / args.csv
    output_dir = PROJECT_ROOT / args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load CaseCards
    logger.info("Loading CaseCards from %s", csv_path)
    cards = load_case_cards_from_csv(csv_path)
    logger.info("Loaded %d patients", len(cards))

    # Initialise tools
    seg_tool = SegmentationTool(device=device)
    cls_tool = ClassificationTool(device=device)
    morph_tool = MorphologyTool()
    wall_tool = WallEvidenceTool()

    # Build vectors
    vectors = []
    metadata = []
    skipped = 0

    for i, card in enumerate(cards):
        if (i + 1) % 50 == 0 or i == 0:
            logger.info("Processing patient %d/%d: %s",
                         i + 1, len(cards), card.patient_id)

        cls_results = []
        morph_results = []
        wall_evidence = {"available": False}

        frames_to_process = card.frames[:args.batch_frames]
        for frame in frames_to_process:
            try:
                # Segmentation
                seg_out = seg_tool.execute(image_path=frame.image_path)
                raw_mask = seg_tool.get_cached_mask(frame.image_path)

                # Wall evidence (best frame with mask)
                if raw_mask is not None and not wall_evidence.get("available"):
                    try:
                        wall_evidence = wall_tool.execute(
                            image_path=frame.image_path,
                            lesion_mask_array=raw_mask,
                        )
                    except Exception as wall_exc:
                        logger.debug("Wall evidence skipped: %s", wall_exc)

                # Classification
                cls_kwargs = {"image_path": frame.image_path}
                if frame.predicted_mask_path:
                    cls_kwargs["mask_path"] = frame.predicted_mask_path
                if frame.roi_path:
                    cls_kwargs["roi_path"] = frame.roi_path
                elif seg_out.get("roi_bbox"):
                    cls_kwargs["roi_bbox"] = seg_out["roi_bbox"]
                elif seg_out.get("mask_available"):
                    raw_mask = seg_tool.get_cached_mask(frame.image_path)
                    if raw_mask is not None:
                        cls_kwargs["mask_array"] = raw_mask

                cls_out = cls_tool.execute(**cls_kwargs)
                cls_results.append(cls_out)

                # Morphology
                mask_path = frame.predicted_mask_path
                if mask_path:
                    morph_out = morph_tool.execute(mask_path=mask_path)
                    morph_results.append(morph_out)
                elif seg_out.get("mask_available"):
                    raw_mask = seg_tool.predict_mask_raw(frame.image_path)
                    if raw_mask is not None:
                        morph_out = morph_tool.execute(mask_array=raw_mask)
                        morph_results.append(morph_out)

            except Exception as e:
                logger.warning("Error processing frame %s: %s",
                                frame.image_path, e)
                continue

        if not cls_results:
            skipped += 1
            continue

        # Clinical
        clin_dict = card.clinical.to_dict() if card.clinical else None

        # Build vector (extended when wall available)
        vec = extract_patient_vector(cls_results, morph_results, clin_dict, wall_evidence)
        vectors.append(vec)

        # Build metadata
        key_features = build_key_features_summary(cls_results, morph_results)
        metadata.append({
            "patient_id": card.patient_id,
            "data_source": card.data_source,
            "T_stage": card.gt_T_stage or "unknown",
            "T_label": card.gt_T_label,
            "key_features": key_features,
        })

    logger.info("Built vectors for %d patients (skipped %d)",
                 len(vectors), skipped)

    if not vectors:
        logger.error("No vectors built, exiting")
        sys.exit(1)

    # Build and save FAISS index
    matrix = np.stack(vectors, axis=0)
    index = CaseIndex(dim=matrix.shape[1])
    index.build(matrix[:, :VECTOR_DIM] if matrix.shape[1] > VECTOR_DIM else matrix, metadata)
    index.save(output_dir)

    np.save(output_dir / "case_matrix_extended.npy", matrix.astype(np.float32))
    with open(output_dir / "case_metadata_extended.json", "w") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    build_manifest = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "csv_path": str(csv_path),
        "output_dir": str(output_dir),
        "vector_dim": int(matrix.shape[1]),
        "legacy_vector_dim": VECTOR_DIM,
        "extended_vector_dim": EXT_VECTOR_DIM,
        "case_count": len(metadata),
        "batch_frames": args.batch_frames,
        "device": str(device),
        "segmentation_model": str(seg_tool._model_path),
        "classification_experiment": str(cls_tool._exp_dir),
    }
    with open(output_dir / "build_manifest.json", "w") as f:
        json.dump(build_manifest, f, indent=2, ensure_ascii=False)

    # Summary statistics
    stages = [m.get("T_stage", "unknown") for m in metadata]
    from collections import Counter
    stage_dist = Counter(stages)
    logger.info("Stage distribution in memory: %s", dict(stage_dist))
    logger.info("Done. Index saved to %s", output_dir)


if __name__ == "__main__":
    main()

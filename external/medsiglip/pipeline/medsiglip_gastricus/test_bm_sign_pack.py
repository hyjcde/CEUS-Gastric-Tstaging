import numpy as np

from .bm_sign_pack import (
    BM_SIGN_DIM,
    encode_fields,
    encode_report,
    fields_from_ultrasound_text,
    parse_lesion_site,
    parse_ulcer_present,
    parse_wall_layers,
)


def test_site_and_wall():
    assert parse_lesion_site("胃体（小弯）") == "胃体（小弯）"
    assert parse_lesion_site("胃窦溃疡") == "胃窦"
    assert parse_wall_layers("胃壁层次清晰") == "存在"
    assert parse_wall_layers("层次模糊") == "模糊"
    assert parse_ulcer_present(True) == 1
    assert parse_ulcer_present("无") == 0
    assert parse_ulcer_present("胃窦溃疡") == 1
    assert parse_ulcer_present("未见溃疡") == 0


def test_encode_empty_is_all_missing():
    vector = encode_fields({})
    assert len(vector) == BM_SIGN_DIM
    assert vector[1] == 1.0
    assert vector[3] == 1.0
    assert vector[5] == 1.0
    assert vector[7] == 1.0
    assert vector[9] == 1.0


def test_encode_report_and_text():
    packed = encode_report({
        "fields": {
            "lesion_site": "胃角",
            "maximum_diameter_cm": 3.2,
            "maximum_thickness_cm": 1.1,
            "ulcer_present": False,
            "wall_layers": "存在",
        }
    })
    assert packed["n_filled"] == 5
    assert packed["vector"][1] == 0.0
    parsed = fields_from_ultrasound_text("胃窦见溃疡，大小约18*8mm，胃壁层次清晰")
    assert parsed["lesion_site"] == "胃窦"
    assert parsed["ulcer_present"] == 1
    assert parsed["wall_layers"] == "存在"
    assert parsed["max_diameter_cm"] == 1.8
    assert parsed["max_thickness_cm"] == 0.8


def test_lora_views_paint_polygon(tmp_path):
    from PIL import Image

    from .preprocess import load_lora_views, overlay_mask_polygon

    image = Image.new("RGB", (64, 48), (20, 20, 20))
    mask = np.zeros((48, 64), dtype=bool)
    mask[10:30, 12:40] = True
    painted = overlay_mask_polygon(image, mask, fill_alpha=0.4, contour=True)
    arr = np.asarray(painted)
    assert arr[20, 25, 0] > arr[2, 2, 0]
    crop = tmp_path / "frame.jpg"
    mask_path = tmp_path / "mask.png"
    image.save(crop)
    Image.fromarray(mask.astype(np.uint8) * 255).save(mask_path)
    full, roi = load_lora_views(crop, mask_path, expand=0.2)
    assert full.size == (64, 48)
    assert roi.size[0] == roi.size[1]
    official = tmp_path / "roi.jpg"
    Image.new("RGB", (20, 16), (80, 80, 80)).save(official)
    full2, roi2 = load_lora_views(crop, mask_path, official_roi=official)
    assert roi2.size[0] == roi2.size[1]
    crop_tree = tmp_path / "crop_ui" / "images"
    roi_tree = tmp_path / "crop_roi" / "images"
    crop_tree.mkdir(parents=True)
    roi_tree.mkdir(parents=True)
    src = crop_tree / "frame.jpg"
    dest = roi_tree / "frame.jpg"
    image.save(src)
    Image.new("RGB", (20, 16), (80, 80, 80)).save(dest)
    from .preprocess import official_roi_from_crop_ui

    assert official_roi_from_crop_ui(src) == dest


if __name__ == "__main__":
    from pathlib import Path
    from tempfile import TemporaryDirectory

    test_site_and_wall()
    test_encode_empty_is_all_missing()
    test_encode_report_and_text()
    with TemporaryDirectory() as tmp:
        test_lora_views_paint_polygon(Path(tmp))
    print("ok")

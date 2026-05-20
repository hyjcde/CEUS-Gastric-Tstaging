#!/usr/bin/env python3
"""
准备医生标注用的 direction_annotation_batch.json 文件。

使用方法:
    python prepare_batch.py --data-root /path/to/data

会扫描 data-root 下的 CSV 文件和 dataset/ 目录，生成 batch JSON。
"""
import argparse
import csv
import json
import os
import sys
from pathlib import Path
from datetime import datetime


def load_labelme_polygon(json_path):
    """从 LabelMe JSON 中提取 tumor 标注的多边形坐标"""
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
        for shape in data.get('shapes', []):
            label = (shape.get('label') or '').lower()
            if label in ('tumor', 'lesion', '病灶') or 'tumor' in label or 'lesion' in label:
                pts = shape.get('points')
                if len(pts) >= 3:
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    centroid = [round(sum(xs)/len(xs), 1), round(sum(ys)/len(ys), 1)]
                    bbox = [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]
                    return centroid, bbox
    except Exception:
        pass
    return None


def find_annotation_path(image_path, data_root):
    """推断 LabelMe 标注文件路径"""
    img_rel = image_path
    base = os.path.splitext(os.path.basename(img_rel))[0]
    img_dir = os.path.dirname(img_rel)
    parent = os.path.dirname(img_dir)
    ann_dir = os.path.join(parent, 'annotations')
    ann_path = os.path.join(ann_dir, base + '.json')
    full = os.path.join(data_root, ann_path)
    if os.path.exists(full):
        return ann_path
    return None


def process_csv(csv_path, data_root, split_name):
    """处理一个 CSV 文件"""
    items = []
    if not os.path.exists(csv_path):
        return items
    
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            image_path = row.get('image_path', '').strip()
            if not image_path:
                continue
            
            full_img = os.path.join(data_root, image_path)
            if not os.path.exists(full_img):
                continue

            ann_path = find_annotation_path(image_path, data_root)
            mask_info = None
            if ann_path:
                mask_info = load_labelme_polygon(os.path.join(data_root, ann_path))

            item = {
                'image_path': image_path,
                'annotation_path': ann_path,
                'patient_id': row.get('patient_id', ''),
                'T_stage': row.get('T_stage', ''),
                'label': int(row.get('label', 0)),
                'source': row.get('source', ''),
                'split': split_name,
                'has_mask': mask_info is not None,
                'mask_centroid': mask_info[0] if mask_info else None,
                'mask_bbox': mask_info[1] if mask_info else None,
            }
            items.append(item)
    return items


def main():
    parser = argparse.ArgumentParser(description='准备突破方向标注批次文件')
    parser.add_argument('--data-root', required=True, help='数据集根目录')
    parser.add_argument('--csv-dir', default=None, help='CSV 文件目录 (默认: data-root/pipeline/data/tstaging_4class/)')
    parser.add_argument('--output', default=None, help='输出文件路径 (默认: data-root/direction_annotation_batch.json)')
    parser.add_argument('--t23-only', action='store_true', help='仅包含 T2/T3')
    args = parser.parse_args()

    data_root = os.path.abspath(args.data_root)
    csv_dir = args.csv_dir or os.path.join(data_root, 'pipeline', 'data', 'tstaging_4class')
    output = args.output or os.path.join(data_root, 'direction_annotation_batch.json')

    print(f"数据目录: {data_root}")
    print(f"CSV 目录: {csv_dir}")

    all_items = []
    for csv_name in ['train.csv', 'val.csv', 'test.csv']:
        csv_path = os.path.join(csv_dir, csv_name)
        split = csv_name.replace('.csv', '')
        items = process_csv(csv_path, data_root, split)
        print(f"  {csv_name}: {len(items)} 张图")
        all_items.extend(items)

    if args.t23_only:
        all_items = [it for it in all_items if it['T_stage'] in ('T2', 'T3')]
        print(f"筛选 T2/T3 后: {len(all_items)} 张")

    # Sort: T2/T3 with masks first
    def sort_key(it):
        is_t23 = 0 if it['T_stage'] in ('T2', 'T3') else 1
        has_m = 0 if it['has_mask'] else 1
        return (is_t23, has_m, it['patient_id'], it['image_path'])
    
    all_items.sort(key=sort_key)

    # Deduplicate by image_path
    seen = set()
    unique = []
    for it in all_items:
        if it['image_path'] not in seen:
            seen.add(it['image_path'])
            unique.append(it)
    all_items = unique

    batch = {
        'batch_name': f'direction_all_{len(all_items)}',
        'created': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total': len(all_items),
        'items': all_items,
    }

    with open(output, 'w') as f:
        json.dump(batch, f, ensure_ascii=False, indent=2)

    print(f"\n生成完成: {output}")
    print(f"共 {len(all_items)} 张图片")

    stages = {}
    for it in all_items:
        s = it['T_stage']
        stages[s] = stages.get(s, 0) + 1
    for s, c in sorted(stages.items()):
        print(f"  {s}: {c}")


if __name__ == '__main__':
    main()

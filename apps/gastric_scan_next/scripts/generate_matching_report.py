#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成详细的匹配分析报告
"""

import json
import os
import re
import pandas as pd
from pathlib import Path

def normalize_id(id_str):
    """标准化ID"""
    if not id_str or id_str == '':
        return None
    id_str = str(id_str).strip()
    if id_str.startswith('Z'):
        id_str = id_str[1:]
    id_str = id_str.lstrip('0')
    return id_str if id_str else None

def find_id_in_files(id_str, all_files, max_check=1000):
    """在文件中查找ID的所有可能变体"""
    variants = [
        id_str,
        f'Z{id_str.zfill(7)}',
        id_str.zfill(7),
        id_str.zfill(8),
        id_str.lstrip('0'),
    ]
    
    found = []
    for variant in variants:
        for fname in all_files[:max_check]:
            if variant in fname:
                found.append(fname)
        if found:
            break
    
    return found

def analyze_matching():
    """分析匹配情况并生成报告"""
    
    base_dir = Path(__file__).parent.parent.parent.parent
    
    print("=" * 80)
    print("匹配分析报告")
    print("=" * 80)
    
    # 分析2024年
    print("\n【2024年数据匹配分析】")
    clinical_2024_path = base_dir / 'gastricTstaging/gastric-scan-next/data/clinical_data_2024.json'
    with open(clinical_2024_path, 'r', encoding='utf-8') as f:
        clinical_2024 = json.load(f)
    
    df_2024 = pd.read_excel(base_dir / '2024/2024年直接手术.xlsx')
    
    # 收集所有图片
    all_images_2024 = []
    for img_dir in [
        base_dir / 'Gastric_Cancer_Dataset_2024/images',
        base_dir / 'Gastric_Cancer_Dataset_2024_Cropped/images'
    ]:
        if img_dir.exists():
            all_images_2024.extend([f for f in img_dir.iterdir() if f.suffix.lower() == '.jpg'])
    
    # 提取ID
    image_ids_2024 = set()
    id_to_files_2024 = {}
    for img_file in all_images_2024:
        fname = img_file.name
        match = re.search(r'Surgery_2024_\d+-([A-Z]?\d+)-', fname)
        if match:
            img_id = normalize_id(match.group(1))
            if img_id:
                image_ids_2024.add(img_id)
                if img_id not in id_to_files_2024:
                    id_to_files_2024[img_id] = []
                id_to_files_2024[img_id].append(fname)
    
    clinical_ids_2024 = set(clinical_2024.keys())
    matched_2024 = clinical_ids_2024 & image_ids_2024
    unmatched_2024 = clinical_ids_2024 - image_ids_2024
    
    print(f"临床数据ID: {len(clinical_ids_2024)}")
    print(f"图片文件ID: {len(image_ids_2024)}")
    print(f"✅ 匹配: {len(matched_2024)} ({len(matched_2024)*100/len(clinical_ids_2024):.1f}%)")
    print(f"❌ 未匹配: {len(unmatched_2024)}")
    
    # 详细检查未匹配的
    if unmatched_2024:
        print(f"\n未匹配ID详情（前10个）:")
        unmatched_list = list(unmatched_2024)[:10]
        all_fnames = [f.name for f in all_images_2024]
        
        for uid in unmatched_list:
            # 在Excel中找到原始ID
            excel_row = df_2024[df_2024['ID'].astype(str).str.replace('Z', '').str.lstrip('0') == uid.lstrip('0')]
            original_id = str(excel_row.iloc[0]['ID']) if len(excel_row) > 0 else uid
            
            # 尝试找到匹配的文件
            found_files = find_id_in_files(uid, all_fnames)
            if not found_files:
                found_files = find_id_in_files(original_id, all_fnames)
            
            print(f"\n  ID: {uid} (Excel原始: {original_id})")
            if found_files:
                print(f"    ✅ 找到匹配: {found_files[0]}")
            else:
                print(f"    ❌ 未找到匹配的文件")
    
    # 分析2025年
    print("\n\n【2025年数据匹配分析】")
    clinical_2025_path = base_dir / 'gastricTstaging/gastric-scan-next/data/clinical_data.json'
    with open(clinical_2025_path, 'r', encoding='utf-8') as f:
        clinical_2025 = json.load(f)
    
    df_2025 = pd.read_excel(base_dir / '2025/2025胃癌临床整理.xlsx')
    
    all_images_2025 = []
    for img_dir in [
        base_dir / 'Gastric_Cancer_Dataset_2025/images',
        base_dir / 'Gastric_Cancer_Dataset_2025_Cropped/images'
    ]:
        if img_dir.exists():
            all_images_2025.extend([f for f in img_dir.iterdir() 
                                  if f.suffix.lower() == '.jpg' and ('Surgery' in f.name or 'Chemo' in f.name)])
    
    image_ids_2025 = set()
    for img_file in all_images_2025:
        fname = img_file.name
        match = re.search(r'(?:Surgery|Chemo)_2025_\w+_(\d+)', fname)
        if match:
            image_ids_2025.add(match.group(1))
    
    clinical_ids_2025 = set(clinical_2025.keys())
    matched_2025 = clinical_ids_2025 & image_ids_2025
    unmatched_2025 = clinical_ids_2025 - image_ids_2025
    
    print(f"临床数据ID: {len(clinical_ids_2025)}")
    print(f"图片文件ID: {len(image_ids_2025)}")
    print(f"✅ 匹配: {len(matched_2025)} ({len(matched_2025)*100/len(clinical_ids_2025):.1f}%)")
    print(f"❌ 未匹配: {len(unmatched_2025)}")
    
    if unmatched_2025:
        print(f"\n未匹配ID详情（前10个）:")
        unmatched_list = list(unmatched_2025)[:10]
        all_fnames = [f.name for f in all_images_2025]
        
        for uid in unmatched_list:
            excel_row = df_2025[df_2025['住院号'].astype(str) == uid]
            name = excel_row.iloc[0]['姓名'] if len(excel_row) > 0 else 'N/A'
            
            found_files = find_id_in_files(uid, all_fnames)
            
            print(f"\n  住院号: {uid} (姓名: {name})")
            if found_files:
                print(f"    ✅ 找到匹配: {found_files[0]}")
            else:
                print(f"    ❌ 未找到匹配的文件")

if __name__ == '__main__':
    analyze_matching()


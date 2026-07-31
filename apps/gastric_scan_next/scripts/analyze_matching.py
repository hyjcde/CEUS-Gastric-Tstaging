#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析图片文件名与临床数据的匹配情况
"""

import os
import re
import json
import pandas as pd

def normalize_id(id_str):
    """标准化ID：去掉Z前缀，去掉前导零"""
    if not id_str or id_str == '':
        return None
    id_str = str(id_str).strip()
    if id_str.startswith('Z'):
        id_str = id_str[1:]
    id_str = id_str.lstrip('0')
    return id_str if id_str else None

def extract_all_possible_ids(filename):
    """从文件名中提取所有可能的ID"""
    ids = set()
    
    # 提取所有数字序列
    numbers = re.findall(r'\d+', filename)
    for num in numbers:
        ids.add(num)
        ids.add(normalize_id(num))
    
    # 提取带Z前缀的
    z_numbers = re.findall(r'Z\d+', filename)
    for z_num in z_numbers:
        ids.add(z_num)
        ids.add(normalize_id(z_num))
    
    # 从特定格式中提取
    # 格式1: Surgery_2024_1-732953-4.jpg
    match1 = re.search(r'[-_](\d{6,})[-_]', filename)
    if match1:
        ids.add(match1.group(1))
        ids.add(normalize_id(match1.group(1)))
    
    # 格式2: Surgery_2024_1-Z0139282-5.jpg
    match2 = re.search(r'[-_](Z\d+)', filename)
    if match2:
        ids.add(match2.group(1))
        ids.add(normalize_id(match2.group(1)))
    
    return {i for i in ids if i}

def analyze_2024():
    """分析2024年数据匹配"""
    print("=" * 80)
    print("2024年数据匹配分析")
    print("=" * 80)
    
    # 读取临床数据
    clinical_path = 'gastricTstaging/gastric-scan-next/data/clinical_data_2024.json'
    with open(clinical_path, 'r', encoding='utf-8') as f:
        clinical = json.load(f)
    
    clinical_ids = set(clinical.keys())
    print(f"\n临床数据ID数量: {len(clinical_ids)}")
    
    # 读取原始Excel
    excel_path = '2024/2024年直接手术.xlsx'
    df = pd.read_excel(excel_path)
    
    # 收集所有图片文件
    image_dirs = [
        'Gastric_Cancer_Dataset_2024/images',
        'Gastric_Cancer_Dataset_2024_Cropped/images'
    ]
    
    all_images = []
    for img_dir in image_dirs:
        if os.path.exists(img_dir):
            files = [(img_dir, f) for f in os.listdir(img_dir) if f.endswith('.jpg')]
            all_images.extend(files)
    
    print(f"图片文件总数: {len(all_images)}")
    
    # 建立ID到文件的映射（使用所有可能的ID）
    id_to_files = {}
    for img_dir, filename in all_images:
        possible_ids = extract_all_possible_ids(filename)
        for pid in possible_ids:
            if pid not in id_to_files:
                id_to_files[pid] = []
            id_to_files[pid].append((img_dir, filename))
    
    print(f"提取的唯一ID数量: {len(id_to_files)}")
    
    # 匹配
    matched = {}
    unmatched = []
    
    for clinical_id in clinical_ids:
        # 尝试直接匹配
        if clinical_id in id_to_files:
            matched[clinical_id] = id_to_files[clinical_id]
        else:
            # 尝试标准化后匹配
            normalized_id = normalize_id(clinical_id)
            if normalized_id and normalized_id in id_to_files:
                matched[clinical_id] = id_to_files[normalized_id]
            else:
                unmatched.append(clinical_id)
    
    print(f"\n✅ 匹配成功: {len(matched)}/{len(clinical_ids)} ({len(matched)*100/len(clinical_ids):.1f}%)")
    print(f"❌ 未匹配: {len(unmatched)}")
    
    # 输出未匹配的详细信息
    if unmatched:
        print(f"\n未匹配的ID详情（前20个）:")
        for uid in unmatched[:20]:
            print(f"  {uid}")
            # 尝试找相似的文件名
            similar_files = []
            for img_dir, filename in all_images[:100]:  # 只检查前100个
                if uid in filename or normalize_id(uid) in filename:
                    similar_files.append(filename)
            if similar_files:
                print(f"    可能的匹配: {similar_files[0]}")
    
    return len(matched), len(unmatched)

def analyze_2025():
    """分析2025年数据匹配"""
    print("\n" + "=" * 80)
    print("2025年数据匹配分析")
    print("=" * 80)
    
    # 读取临床数据
    clinical_path = 'gastricTstaging/gastric-scan-next/data/clinical_data.json'
    with open(clinical_path, 'r', encoding='utf-8') as f:
        clinical = json.load(f)
    
    clinical_ids = set(clinical.keys())
    print(f"\n临床数据ID数量: {len(clinical_ids)}")
    
    # 收集所有图片文件
    image_dirs = [
        'Gastric_Cancer_Dataset_2025/images',
        'Gastric_Cancer_Dataset_2025_Cropped/images'
    ]
    
    all_images = []
    for img_dir in image_dirs:
        if os.path.exists(img_dir):
            files = [(img_dir, f) for f in os.listdir(img_dir) 
                    if f.endswith('.jpg') and ('Surgery' in f or 'Chemo' in f)]
            all_images.extend(files)
    
    print(f"图片文件总数: {len(all_images)}")
    
    # 提取ID
    id_to_files = {}
    for img_dir, filename in all_images:
        # 格式: Surgery_2025_1M_1457633 (1).jpg
        match = re.search(r'(?:Surgery|Chemo)_2025_\w+_(\d+)', filename)
        if match:
            hosp_id = match.group(1)
            if hosp_id not in id_to_files:
                id_to_files[hosp_id] = []
            id_to_files[hosp_id].append((img_dir, filename))
    
    print(f"提取的唯一ID数量: {len(id_to_files)}")
    
    # 匹配
    matched = {}
    unmatched = []
    
    for clinical_id in clinical_ids:
        if clinical_id in id_to_files:
            matched[clinical_id] = id_to_files[clinical_id]
        else:
            unmatched.append(clinical_id)
    
    print(f"\n✅ 匹配成功: {len(matched)}/{len(clinical_ids)} ({len(matched)*100/len(clinical_ids):.1f}%)")
    print(f"❌ 未匹配: {len(unmatched)}")
    
    if unmatched:
        print(f"\n未匹配的ID详情（前20个）:")
        for uid in unmatched[:20]:
            print(f"  {uid}")
            # 在所有文件名中搜索
            similar_files = [f for img_dir, f in all_images if uid in f]
            if similar_files:
                print(f"    找到匹配: {similar_files[0]}")
    
    return len(matched), len(unmatched)

if __name__ == '__main__':
    matched_2024, unmatched_2024 = analyze_2024()
    matched_2025, unmatched_2025 = analyze_2025()
    
    print("\n" + "=" * 80)
    print("总结")
    print("=" * 80)
    print(f"2024年: {matched_2024} 匹配, {unmatched_2024} 未匹配")
    print(f"2025年: {matched_2025} 匹配, {unmatched_2025} 未匹配")


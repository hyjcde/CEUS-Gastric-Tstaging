#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将Excel文件转换为系统所需的JSON格式临床数据
"""

import pandas as pd
import json
import os
import sys
from pathlib import Path

# 肿瘤位置映射
LOCATION_MAP = {
    0: "Cardia/Fundus",  # 贲门、胃底
    1: "Body",           # 胃体
    2: "Angle/Antrum",   # 胃角、胃窦
    3: "Whole Stomach"   # 全胃
}

# 性别映射
SEX_MAP = {
    0: "Female",
    1: "Male",
    "女": "Female",
    "男": "Male",
    "Female": "Female",
    "Male": "Male"
}

# 分化程度映射
DIFFERENTIATION_MAP = {
    1: "Well Differentiated",
    2: "Moderately Differentiated",
    3: "Moderately-Poorly Differentiated",
    4: "Poorly Differentiated",
    5: "Undetermined"
}

# Lauren分型映射
LAUREN_MAP = {
    1: "1",  # 肠型
    2: "2",  # 弥漫型
    3: "3",  # 混合型
    4: "4"   # 不确定
}

def safe_float(value):
    """安全转换为float"""
    try:
        if pd.isna(value) or value == '' or str(value).strip() == '':
            return None
        return float(value)
    except:
        return None

def safe_str(value):
    """安全转换为字符串"""
    if pd.isna(value):
        return ""
    return str(value).strip()

def safe_int(value):
    """安全转换为整数"""
    try:
        if pd.isna(value):
            return None
        return int(float(value))
    except:
        return None

def normalize_id(id_str):
    """标准化ID：去掉Z前缀，去掉前导零，用于匹配"""
    if pd.isna(id_str) or id_str == '':
        return None
    id_str = str(id_str).strip()
    # 去掉Z前缀
    if id_str.startswith('Z'):
        id_str = id_str[1:]
    # 去掉前导零（但保留至少一位数字）
    id_str = id_str.lstrip('0')
    return id_str if id_str else None

def convert_sex(value):
    """转换性别"""
    if pd.isna(value):
        return "Unknown"
    value = str(value).strip()
    if value in SEX_MAP:
        return SEX_MAP[value]
    # 尝试数字转换
    try:
        num_val = int(float(value))
        return SEX_MAP.get(num_val, "Unknown")
    except:
        return "Unknown"

def convert_location(value):
    """转换肿瘤位置"""
    if pd.isna(value):
        return "Unknown"
    try:
        num_val = int(float(value))
        return LOCATION_MAP.get(num_val, "Unknown")
    except:
        return "Unknown"

def convert_differentiation(value):
    """转换分化程度"""
    if pd.isna(value):
        return "Undetermined"
    try:
        num_val = int(float(value))
        return DIFFERENTIATION_MAP.get(num_val, "Undetermined")
    except:
        return "Undetermined"

def convert_lauren(value):
    """转换Lauren分型"""
    if pd.isna(value):
        return "4"
    try:
        num_val = int(float(value))
        return LAUREN_MAP.get(num_val, "4")
    except:
        return "4"

def extract_concept_features(row, pathology_text=""):
    """从病理文本中提取概念特征"""
    features = {}
    
    # 提取Ki67
    if 'ki67' in row and pd.notna(row['ki67']):
        ki67_val = safe_str(row['ki67'])
        if ki67_val:
            features['ki67'] = f"Ki67约{ki67_val}%" if '%' not in ki67_val else ki67_val
    
    # 提取CPS
    if 'CPS' in row and pd.notna(row['CPS']):
        cps_val = safe_str(row['CPS'])
        if cps_val:
            features['cps'] = f"CPS{cps_val}" if not cps_val.startswith('CPS') else cps_val
    
    # 提取PD-1
    if 'PD-1' in row and pd.notna(row['PD-1']):
        pd1_val = safe_str(row['PD-1'])
        if pd1_val:
            features['pd1'] = f"PD-1{pd1_val}"
    
    # 提取FoxP3
    if 'FoxP3' in row and pd.notna(row['FoxP3']):
        foxp3_val = safe_str(row['FoxP3'])
        if foxp3_val:
            features['foxp3'] = f"FoxP3{foxp3_val}"
    
    # 提取CD3/CD4/CD8
    if 'CD3、CD4、CD8' in row and pd.notna(row['CD3、CD4、CD8']):
        cd3_val = safe_str(row['CD3、CD4、CD8'])
        if cd3_val:
            features['cd3'] = cd3_val
            features['cd4'] = cd3_val
    
    # 从病理文本中提取血管和神经侵犯信息
    if pathology_text:
        if '脉管' in pathology_text or '血管' in pathology_text:
            features['vascular'] = "脉管内瘤栓" if '瘤栓' in pathology_text else "脉管侵犯"
        if '神经' in pathology_text:
            features['neural'] = "神经侵犯"
    
    return features if features else None

def convert_2024_excel(input_path, output_path):
    """转换2024年Excel文件"""
    print(f"正在读取: {input_path}")
    df = pd.read_excel(input_path)
    print(f"读取到 {len(df)} 条记录")
    
    result = {}
    
    for idx, row in df.iterrows():
        # 使用标准化的ID作为key，以便与图片文件名匹配
        if pd.notna(row['ID']):
            original_id = str(row['ID']).strip()
            # 标准化ID（去掉Z前缀和前导零）
            patient_id = normalize_id(original_id)
            # 如果标准化后为空，使用原始ID
            if not patient_id:
                patient_id = original_id
        else:
            patient_id = None
        
        if not patient_id:
            continue
        
        # 基本信息
        age = safe_float(row['年龄'])
        sex = convert_sex(row['性别： 0=女， 1=男'])
        
        # 肿瘤大小
        tumor_size = {
            "length": safe_float(row.get('长径：cm')),
            "thickness": safe_float(row.get('厚径：cm'))
        }
        
        # 肿瘤位置
        location = convert_location(row.get('肿瘤位置0=贲门、胃底，1=胃体，2=胃角、胃窦，3=全胃'))
        
        # 生物标志物
        cea = safe_float(row.get('CEA'))
        ca199 = safe_float(row.get('CA199'))
        cea_positive = bool(safe_int(row.get('CEA：0=阴性， 1=阳性')))
        ca199_positive = bool(safe_int(row.get('CA199:  0=阴性，  1=阳性 ')))
        
        biomarkers = {
            "cea": cea,
            "ca199": ca199,
            "cea_positive": cea_positive,
            "ca199_positive": ca199_positive
        }
        
        # 病理信息
        pathology_text = safe_str(row.get('病理', ''))
        differentiation = convert_differentiation(row.get('分化程度（1=高分化，2=中分化，3=中-低分化，4=低分化，5=不确定）'))
        lauren = convert_lauren(row.get('Lauren分型（1.肠型，2.弥漫型，3混合型，4不确定）'))
        
        # 分期信息
        pT_col = 'pT:1=T1（局限在粘膜及粘膜下层），2=T2（肿瘤侵犯肌层及浆膜下层），3=T3（肿瘤侵透浆膜层），4=T4a（侵犯较浅且到达了浆膜层），5=T4b（侵犯较深且到达了邻近组织或脏器）'
        pT = safe_str(row.get(pT_col, ''))
        pN_col = 'N:0=N0，1=N1，2=N2，3=N3a，4=3b'
        pN = safe_str(row.get(pN_col, ''))
        pM_col = 'M：0=没有远处转移，   1=有远处转移'
        pM = safe_str(row.get(pM_col, '0'))
        pStage_col = 'pStage(1=I;2=II;3=III,4=IV)'
        pStage = safe_str(row.get(pStage_col, ''))
        
        pathology = {
            "type": pathology_text,
            "differentiation": differentiation,
            "lauren": lauren,
            "pT": pT,
            "pN": pN,
            "pM": pM,
            "pStage": pStage
        }
        
        # 概念特征
        concept_features = extract_concept_features(row, pathology_text)
        
        # 构建完整记录
        record = {
            "age": age,
            "sex": sex,
            "tumorSize": tumor_size,
            "location": location,
            "biomarkers": biomarkers,
            "pathology": pathology
        }
        
        if concept_features:
            record["concept_features"] = concept_features
        
        result[patient_id] = record
    
    # 保存JSON
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"成功转换 {len(result)} 条记录到: {output_path}")
    return result

def convert_2025_excel(input_path, output_path):
    """转换2025年Excel文件"""
    print(f"正在读取: {input_path}")
    df = pd.read_excel(input_path)
    print(f"读取到 {len(df)} 条记录")
    
    result = {}
    
    for idx, row in df.iterrows():
        # 使用标准化的住院号作为key，以便与图片文件名匹配
        original_hosp = safe_str(row.get('住院号', ''))
        if not original_hosp or original_hosp == '':
            continue
        # 对于2025年，保留原始格式（包括Z前缀），同时创建标准化版本
        # 如果原始ID是Z格式，保留Z格式；如果是纯数字，标准化
        if original_hosp.startswith('Z'):
            # Z格式直接使用
            patient_id = original_hosp
        else:
            # 纯数字格式，标准化（去掉前导零）
            patient_id = normalize_id(original_hosp)
            if not patient_id:
                patient_id = original_hosp
        
        # 基本信息
        age = safe_float(row.get('年龄'))
        sex_str = safe_str(row.get('性别： 0=女， 1=男', ''))
        # 2025年性别可能是中文
        if sex_str in ['女', 'Female']:
            sex = "Female"
        elif sex_str in ['男', 'Male']:
            sex = "Male"
        else:
            sex = convert_sex(row.get('性别： 0=女， 1=男'))
        
        # 肿瘤大小
        tumor_size = {
            "length": safe_float(row.get('长径：cm')),
            "thickness": safe_float(row.get('厚径：cm'))
        }
        
        # 肿瘤位置
        location = convert_location(row.get('肿瘤位置0=贲门、胃底，1=胃体，2=胃角、胃窦，3=全胃'))
        
        # 生物标志物
        cea = safe_float(row.get('CEA'))
        ca199 = safe_float(row.get('CA199'))
        cea_positive = bool(safe_int(row.get('CEA：0=阴性， 1=阳性')))
        ca199_positive = bool(safe_int(row.get('CA199：0=阴性， 1=阳性')))
        
        biomarkers = {
            "cea": cea,
            "ca199": ca199,
            "cea_positive": cea_positive,
            "ca199_positive": ca199_positive
        }
        
        # 病理信息
        pathology_text = safe_str(row.get('病理', ''))
        differentiation = convert_differentiation(row.get('分化程度（1=高分化，2=中分化，3=中-低分化，4=低分化，5=不确定）'))
        lauren = convert_lauren(row.get('Lauren分型（1.肠型，2.弥漫型，3混合型，4不确定）'))
        
        # 分期信息
        pT_col = 'pT:1=T1（局限在粘膜及粘膜下层），2=T2（肿瘤侵犯肌层及浆膜下层），3=T3（肿瘤侵透浆膜层），4=T4a（侵犯较浅且到达了浆膜层），5=T4b（侵犯较深且到达了邻近组织或脏器）'
        pT = safe_str(row.get(pT_col, ''))
        pN_col = 'N:0=N0，1=N1，2=N2，3=N3a，4=3b'
        pN = safe_str(row.get(pN_col, ''))
        pM_col = 'M：0=没有远处转移，   1=有远处转移'
        pM = safe_str(row.get(pM_col, '0'))
        pStage_col = 'pStage(1=I;2=II;3=III,4=IV)'
        pStage = safe_str(row.get(pStage_col, ''))
        
        pathology = {
            "type": pathology_text,
            "differentiation": differentiation,
            "lauren": lauren,
            "pT": pT,
            "pN": pN,
            "pM": pM,
            "pStage": pStage
        }
        
        # 概念特征（2025年数据可能需要从病理文本中提取）
        concept_features = {}
        if pathology_text:
            # 从病理文本中提取Ki67
            if 'Ki67' in pathology_text or 'ki67' in pathology_text:
                import re
                ki67_match = re.search(r'Ki67[约约]?(\d+)[%％]', pathology_text)
                if ki67_match:
                    concept_features['ki67'] = f"Ki67约{ki67_match.group(1)}%"
            
            # 提取CPS
            if 'CPS' in pathology_text:
                cps_match = re.search(r'CPS[约约]?([<>]?[\d.]+)', pathology_text)
                if cps_match:
                    concept_features['cps'] = f"CPS{cps_match.group(1)}"
            
            # 提取PD-1
            if 'PD-1' in pathology_text:
                concept_features['pd1'] = "PD-1个别阳性" if '个别' in pathology_text else "PD-1阳性"
            
            # 提取FoxP3
            if 'FoxP3' in pathology_text:
                concept_features['foxp3'] = "FoxP3个别阳性" if '个别' in pathology_text else "FoxP3阳性"
            
            # 提取CD3/CD4/CD8
            if 'CD3' in pathology_text or 'CD4' in pathology_text or 'CD8' in pathology_text:
                concept_features['cd3'] = "CD3、CD4、CD8淋巴细胞部分阳性"
                concept_features['cd4'] = "CD4、CD8淋巴细胞部分阳性"
            
            if '脉管' in pathology_text or '血管' in pathology_text:
                concept_features['vascular'] = "脉管内瘤栓" if '瘤栓' in pathology_text else "脉管侵犯"
            if '神经' in pathology_text:
                concept_features['neural'] = "神经侵犯"
        
        # 构建完整记录
        record = {
            "age": age,
            "sex": sex,
            "tumorSize": tumor_size,
            "location": location,
            "biomarkers": biomarkers,
            "pathology": pathology
        }
        
        if concept_features:
            record["concept_features"] = concept_features
        
        result[patient_id] = record
    
    # 保存JSON
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"成功转换 {len(result)} 条记录到: {output_path}")
    return result

def convert_gist_excel(input_path, output_path):
    """转换GIST Excel文件"""
    print(f"正在读取: {input_path}")
    df = pd.read_excel(input_path)
    print(f"读取到 {len(df)} 条记录")
    
    result = {}
    
    for idx, row in df.iterrows():
        # GIST数据可能使用病例号或住院号作为ID
        # 优先使用住院号，如果没有则使用病例号
        patient_id = None
        
        if pd.notna(row.get('住院号')):
            try:
                # 尝试转换为整数
                patient_id = str(int(float(row['住院号'])))
            except:
                # 如果不能转换为整数，直接使用字符串
                patient_id = str(row['住院号']).strip()
        elif pd.notna(row.get('病例号')):
            patient_id = safe_str(row['病例号'])
        
        if not patient_id or patient_id == '':
            continue
        
        # 基本信息
        age_str = safe_str(row.get('年龄', ''))
        age = None
        if age_str:
            # 处理"73岁"这样的格式
            import re
            age_match = re.search(r'(\d+)', age_str)
            if age_match:
                age = float(age_match.group(1))
        
        sex = convert_sex(row.get('性别', ''))
        
        # 肿瘤大小 - GIST使用long diameter和short diameter
        tumor_size = {
            "length": safe_float(row.get('long diameter')),
            "thickness": safe_float(row.get('short diameter'))
        }
        
        # GIST没有标准的位置字段，设为Unknown
        location = "Unknown"
        
        # GIST没有CEA和CA199
        biomarkers = {
            "cea": None,
            "ca199": None,
            "cea_positive": False,
            "ca199_positive": False
        }
        
        # GIST病理信息 - 从影像所见和印象中构建
        pathology_text = ""
        if pd.notna(row.get('影像所见')):
            pathology_text += safe_str(row.get('影像所见'))
        if pd.notna(row.get('印象')):
            pathology_text += "\n" + safe_str(row.get('印象'))
        
        # GIST特有的概念特征
        concept_features = {}
        
        # Ki67
        if pd.notna(row.get('Ki67')):
            ki67_val = safe_str(row.get('Ki67'))
            if ki67_val:
                concept_features['ki67'] = f"Ki67约{ki67_val}%" if '%' not in ki67_val else ki67_val
        
        # GIST风险等级
        if pd.notna(row.get('GISTs biological risk')):
            risk = safe_str(row.get('GISTs biological risk'))
            if risk:
                concept_features['gist_risk'] = risk
        
        # 基因检测信息
        gene_mutations = []
        for gene in ['KIT-9', 'KIT-11', 'KIT-13', 'KIT-14', 'KIT-17', 'KIT-18', 
                     'PDGFRA-12', 'PDGFRA-14', 'PDGFRA-18']:
            if pd.notna(row.get(gene)):
                val = safe_str(row.get(gene))
                if val and val != '野生型' and val != 'NaN':
                    gene_mutations.append(f"{gene}: {val}")
        
        if gene_mutations:
            concept_features['gene_mutations'] = "; ".join(gene_mutations)
        
        # mitosis
        if pd.notna(row.get('mitosis（换算后）')):
            mitosis = safe_str(row.get('mitosis（换算后）'))
            if mitosis:
                concept_features['mitosis'] = mitosis
        
        pathology = {
            "type": pathology_text if pathology_text else "GIST",
            "differentiation": "Undetermined",  # GIST不使用分化程度
            "lauren": "4",  # GIST不使用Lauren分型
            "pT": "",
            "pN": "",
            "pM": "",
            "pStage": ""
        }
        
        # 构建完整记录
        record = {
            "age": age,
            "sex": sex,
            "tumorSize": tumor_size,
            "location": location,
            "biomarkers": biomarkers,
            "pathology": pathology
        }
        
        if concept_features:
            record["concept_features"] = concept_features
        
        result[patient_id] = record
    
    # 保存JSON
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"成功转换 {len(result)} 条记录到: {output_path}")
    return result

def main():
    base_dir = Path(__file__).parent.parent.parent.parent
    data_dir = Path(__file__).parent.parent / 'data'
    
    # 确保输出目录存在
    data_dir.mkdir(parents=True, exist_ok=True)
    
    results = {}
    
    # 转换2024年数据
    excel_2024 = base_dir / '2024' / '2024年直接手术.xlsx'
    output_2024 = data_dir / 'clinical_data_2024.json'
    if excel_2024.exists():
        results['2024'] = convert_2024_excel(str(excel_2024), str(output_2024))
    else:
        print(f"警告: 文件不存在 {excel_2024}")
    
    # 转换2025年数据
    excel_2025 = base_dir / '2025' / '2025胃癌临床整理.xlsx'
    output_2025 = data_dir / 'clinical_data.json'  # 2025年是默认的
    if excel_2025.exists():
        results['2025'] = convert_2025_excel(str(excel_2025), str(output_2025))
    else:
        print(f"警告: 文件不存在 {excel_2025}")
    
    # 转换GIST数据
    excel_gist = base_dir / 'gist' / 'GIST2025.5.22' / '汇总（18-23整理）25.4.14.xlsx'
    output_gist = data_dir / 'clinical_data_gist.json'
    if excel_gist.exists():
        results['gist'] = convert_gist_excel(str(excel_gist), str(output_gist))
    else:
        print(f"警告: 文件不存在 {excel_gist}")
    
    # 打印总结
    print("\n" + "=" * 80)
    print("转换完成总结")
    print("=" * 80)
    for dataset, data in results.items():
        print(f"{dataset}: {len(data)} 条记录")
    
    return results

if __name__ == '__main__':
    main()


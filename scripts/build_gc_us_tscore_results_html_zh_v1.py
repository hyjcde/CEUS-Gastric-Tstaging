#!/usr/bin/env python3
"""Build the Chinese GC-US T-score results page with a feature formula dictionary."""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = (
    PROJECT_ROOT
    / "pipeline/experiments/reports/gc_us_tscore_feature_stats_v1"
)
PACK_META = (
    PROJECT_ROOT
    / "pipeline/data/gc_us_tscore_features_v1/feature_pack_v1/meta.json"
)
DEFAULT_OUT = REPORT_ROOT / "index.html"

SPLIT_ZH = {
    "train": "训练集",
    "val": "验证集",
    "test_prospective": "前瞻测试集",
    "test_external": "外部测试集",
    "holdout": "保留集",
}

GROUP_ZH = {
    "core": "轮廓形态与毛刺核心",
    "wall_layer": "胃壁软代理",
    "size_covariates": "大小协变量",
    "markers": "肿瘤标志物",
    "seg_geometry": "分割几何",
    "dynamics": "多帧动态",
    "controls": "控制变量",
    "growth_watch": "生长和突破观察项",
    "image_channels_weak": "图像边界弱通道",
}

FEATURES_ZH = [
    {
        "group": "size_covariates",
        "feature": "tumor_length_cm",
        "input": "临床患者表中的病灶最大长径。",
        "formula": "直接读取，不从当前分割 mask 重新计算。",
        "unit": "cm",
        "aggregation": "患者级临床字段",
        "note": "主要大小变量，和厚度、最大径存在共线性。",
    },
    {
        "group": "size_covariates",
        "feature": "tumor_thickness_cm",
        "input": "临床患者表中的病灶最大厚径。",
        "formula": "直接读取，不从当前分割 mask 重新计算。",
        "unit": "cm",
        "aggregation": "患者级临床字段",
        "note": "主要大小变量。",
    },
    {
        "group": "size_covariates",
        "feature": "size_max_diameter_cm",
        "input": "tumor_length_cm 和 tumor_thickness_cm。",
        "formula": "max(长径, 厚径)。",
        "unit": "cm",
        "aggregation": "患者级派生变量",
        "note": "不是新的独立测量，和长径、厚径高度相关。",
    },
    {
        "group": "size_covariates",
        "feature": "size_thickness_length_ratio",
        "input": "tumor_thickness_cm 和 tumor_length_cm。",
        "formula": "厚径 / max(长径, 0.1)。",
        "unit": "无量纲",
        "aggregation": "患者级派生变量",
        "note": "反映相对厚度，但分母含长径，方向不能脱离大小一起解释。",
    },
    {
        "group": "size_covariates",
        "feature": "morph_area_px",
        "input": "预测病灶 mask 的最大外轮廓。",
        "formula": "OpenCV contourArea，单位为像素面积。",
        "unit": "px^2",
        "aggregation": "有效帧按患者取 median",
        "note": "大小代理，不是病灶真实物理面积。",
    },
    {
        "group": "size_covariates",
        "feature": "morph_perimeter_px",
        "input": "预测病灶 mask 的最大外轮廓。",
        "formula": "OpenCV arcLength(contour, closed=True)。",
        "unit": "px",
        "aggregation": "有效帧按患者取 median",
        "note": "和病灶大小及边界复杂度同时相关。",
    },
    {
        "group": "seg_geometry",
        "feature": "seg_short_axis_ratio",
        "input": "预测病灶 mask 的外接矩形和原图尺寸。",
        "formula": "min(外接框宽, 外接框高) / max(图像宽, 图像高)。",
        "unit": "无量纲",
        "aggregation": "沿用既有患者表字段",
        "note": "名称虽叫 short-axis ratio，实际是归一化外接框短边，不是短轴/长轴。",
    },
    {
        "group": "controls",
        "feature": "seg_irregularity",
        "input": "预测病灶 mask 的像素边界和面积。",
        "formula": "log(1 + P^2 / (A + 1e-6))，P 为边界像素数，A 为 mask 像素面积。",
        "unit": "无量纲",
        "aggregation": "沿用既有患者表字段",
        "note": "旧版粗糙度控制变量，容易受 mask 锯齿和大小影响。",
    },
    {
        "group": "core",
        "feature": "morph_circularity",
        "input": "最大外轮廓面积 A 和周长 P。",
        "formula": "4 x pi x A / P^2，最后上限截断为 2。",
        "unit": "无量纲",
        "aggregation": "有效帧按患者取 median",
        "note": "圆形或紧致形状较高；不规则、细长或锯齿形状较低。",
    },
    {
        "group": "core",
        "feature": "morph_solidity",
        "input": "病灶轮廓面积 A 和其凸包面积 A_hull。",
        "formula": "A / A_hull。",
        "unit": "0 到 1",
        "aggregation": "有效帧按患者取 median",
        "note": "越低表示凹陷、分叶或外轮廓不紧致。",
    },
    {
        "group": "core",
        "feature": "morph_concavity_ratio",
        "input": "病灶轮廓面积 A 和凸包面积 A_hull。",
        "formula": "(A_hull - A) / A_hull，近似 1 - solidity。",
        "unit": "0 到 1",
        "aggregation": "有效帧按患者取 median",
        "note": "和 solidity 不是独立信息。",
    },
    {
        "group": "core",
        "feature": "morph_nrl_roughness",
        "input": "重采样后的闭合轮廓。",
        "formula": "以轮廓质心为中心计算径向距离 d，归一化后做 7 点环形移动平均；取相邻 NRL 差值绝对值的均值。",
        "unit": "无量纲",
        "aggregation": "有效帧按患者取 median",
        "note": "描述连续轮廓起伏，不等同于临床毛刺诊断。",
    },
    {
        "group": "core",
        "feature": "morph_peak_sharpness_max",
        "input": "256 点重采样轮廓的径向距离曲线。",
        "formula": "7 点平滑后寻找局部峰；峰值至少达到 1.08 x mean(d)，峰间距至少 8 点；峰高 = d_peak - mean(d)，宽度为半高宽，sharpness = 峰高 / 宽度，取所有峰的最大值。",
        "unit": "归一化轮廓单位",
        "aggregation": "先在帧内取最大峰，再按患者取 median",
        "note": "高值提示窄而尖的外凸，但会受 mask 形状影响。",
    },
    {
        "group": "core",
        "feature": "margin_shape_solidity",
        "input": "预测病灶 mask 的轮廓和凸包。",
        "formula": "轮廓面积 / 凸包面积。",
        "unit": "0 到 1",
        "aggregation": "有效帧按患者取 median",
        "note": "与 morph_solidity 的计算定义高度重复，用于边界通道的独立整理。",
    },
    {
        "group": "core",
        "feature": "margin_shape_fd_high",
        "input": "重采样轮廓的径向距离 NRL。",
        "formula": "15 点强平滑后做 rFFT；取频率 bin 13 到 30 的功率和 / 去直流总功率。",
        "unit": "功率比例",
        "aggregation": "有效帧按患者取 median",
        "note": "中高频轮廓起伏代理；非常高频段被视为标注噪声。",
    },
    {
        "group": "image_channels_weak",
        "feature": "margin_bof_high_mean",
        "input": "灰度图、mask 质心和等效半径。",
        "formula": "在 0.90、1.05、1.20、1.35 倍等效半径的圆周上采样 128 点；每条圆周做 rFFT，取 bin 13 以上高频功率比例，再对尺度求均值。",
        "unit": "功率比例",
        "aggregation": "有效帧按患者取 median",
        "note": "图像边界频谱辅助项，容易受超声 speckle 影响。",
    },
    {
        "group": "image_channels_weak",
        "feature": "margin_clear_robust",
        "input": "soft boundary band 内的径向梯度、内外 rim 灰度差和梯度强度。",
        "formula": "clip(0.45 x ((NRG+1)/2) + 0.30 x tanh(|contrast|/25) + 0.25 x tanh(MI/0.6), 0, 1)；MI 为边界带平均梯度 / 全图梯度 P90。",
        "unit": "0 到 1",
        "aggregation": "有效帧按患者取 median",
        "note": "高值更像清晰锐利边界；当前仅作弱通道，方向需外部验证。",
    },
    {
        "group": "core",
        "feature": "margin_spic_robust",
        "input": "NRL 高频形状、凸性、圆周图像频谱和 needle-like 频谱。",
        "formula": "clip(0.35 x min(FD_high/0.20,1) + 0.25 x (1-solidity) + 0.20 x tanh(BoF_high/0.25) + 0.10 x needle + 0.10 x tanh(BoF_peakiness/8), 0, 1)。",
        "unit": "0 到 1",
        "aggregation": "有效帧按患者取 median",
        "note": "综合毛刺候选指数，不是人工确认的毛刺标签。",
    },
    {
        "group": "wall_layer",
        "feature": "wall_depth_frac_p90",
        "input": "病灶 mask、胃腔 mask 和可选外壁 mask。",
        "formula": "SDF = lumen 外部距离 - lumen 内部距离；病灶正侧 SDF / 估计壁厚；取正值的 P90。",
        "unit": "相对壁深度",
        "aggregation": "帧内 P90 后按患者取 median",
        "note": "外壁存在时壁厚取外壁 SDF P75，否则取健康 shell SDF P80；是胃壁深度软代理。",
    },
    {
        "group": "wall_layer",
        "feature": "wall_serosa_interrupt",
        "input": "病灶 mask、外壁 mask 或 wall depth fraction。",
        "formula": "有外壁时 = 病灶与 5 x 5 膨胀外壁的交集 / 膨胀外壁面积；无外壁时 = depth_frac >= 1.15 的病灶像素比例。",
        "unit": "0 到 1",
        "aggregation": "有效帧按患者取 median",
        "note": "浆膜线中断代理，不是真实浆膜线人工标注。",
    },
    {
        "group": "wall_layer",
        "feature": "wall_v2_pen_ratio_sector",
        "input": "病灶 mask、胃腔 mask，必要时使用外壁 mask。",
        "formula": "以胃腔轮廓 96 点和外法线构造合成浆膜；沿最深点两侧各 8 个点计算 (local_thick - remain) / local_thick，取该扇区 P90。",
        "unit": "相对穿透比例，允许轻微超过 1",
        "aggregation": "帧内最深接触扇区后按患者取 median",
        "note": "沿突破方向计算，但合成浆膜不是组织学浆膜。",
    },
    {
        "group": "wall_layer",
        "feature": "wall_v2_composite",
        "input": "wall_v2_pen_ratio、serosa_proxy 和 echo_loss。",
        "formula": "clip(0.45 x min(pen,1.2)/1.2 + 0.35 x serosa_proxy + 0.20 x echo_loss, 0, 1)。",
        "unit": "0 到 1",
        "aggregation": "有效帧按患者取 median",
        "note": "几何和回声破坏的综合软代理。",
    },
    {
        "group": "wall_layer",
        "feature": "wall_v2_remain_px",
        "input": "合成浆膜点到病灶的距离。",
        "formula": "在最小 remain 的突破方向上，取最近病灶距离和沿内法线首次命中病灶距离的较小值。",
        "unit": "px",
        "aggregation": "帧内取最深点后按患者取 median",
        "note": "数值越低表示越接近浆膜；不是组织厚度实测值。",
    },
    {
        "group": "wall_layer",
        "feature": "wall_v2_serosa_proxy",
        "input": "remain、局部壁厚、overshoot 和 penetration。",
        "formula": "clip(0.50 x (1-remain/thick) + 0.30 x min(overshoot,1) + 0.20 x min(pen,1), 0, 1)。",
        "unit": "0 到 1",
        "aggregation": "有效帧按患者取 median",
        "note": "合成浆膜接近度代理。",
    },
    {
        "group": "wall_layer",
        "feature": "wall_fuse_serosa_remain",
        "input": "wall_serosa_interrupt 和 wall_v2_remain_px。",
        "formula": "0.5 x rank_pct(serosa_interrupt) + 0.5 x rank_pct(-remain_px)。",
        "unit": "0 到 1，队列内 rank",
        "aggregation": "在合并队列上做百分位秩后患者级生成",
        "note": "不是物理量，受当前队列分布影响，主要用于探索性融合。",
    },
    {
        "group": "dynamics",
        "feature": "dyn_invasion_agree",
        "input": "多帧的 morphology、margin、growth、wall 高值或低值比例。",
        "formula": "对可用一致性比例取均值；包括各 frac_high，以及 solidity 的 frac_low 和 remain 的 frac_low。",
        "unit": "0 到 1",
        "aggregation": "先按患者汇总各帧，再对可用比例求 mean",
        "note": "表示多帧是否反复出现侵袭性征象，不是单帧最大值。",
    },
    {
        "group": "dynamics",
        "feature": "morph_peak_sharpness_max__frac_high",
        "input": "每帧 morph_peak_sharpness_max。",
        "formula": "有效帧中 morph_peak_sharpness_max >= 0.35 的比例。",
        "unit": "0 到 1",
        "aggregation": "患者级帧比例",
        "note": "高值表示尖峰在多帧中反复出现。",
    },
    {
        "group": "dynamics",
        "feature": "margin_spic_robust__frac_high",
        "input": "每帧 margin_spic_robust。",
        "formula": "有效帧中 margin_spic_robust >= 0.35 的比例。",
        "unit": "0 到 1",
        "aggregation": "患者级帧比例",
        "note": "用于稳定性而非单帧极值。",
    },
    {
        "group": "dynamics",
        "feature": "bt_v2_max_outward_depth__frac_high",
        "input": "每帧 bt_v2_max_outward_depth。",
        "formula": "有效帧中突破深度 >= 8 px 的比例。",
        "unit": "0 到 1",
        "aggregation": "患者级帧比例",
        "note": "突破重设计观察项。",
    },
    {
        "group": "dynamics",
        "feature": "wall_v2_remain_px__frac_low",
        "input": "每帧 wall_v2_remain_px。",
        "formula": "有效帧中 remain <= 4 px 的比例。",
        "unit": "0 到 1",
        "aggregation": "患者级帧比例",
        "note": "低 remain 代表更接近合成浆膜；不要和真实壁层 GT 混同。",
    },
    {
        "group": "dynamics",
        "feature": "wall_serosa_interrupt__frac_high",
        "input": "每帧 wall_serosa_interrupt。",
        "formula": "有效帧中 serosa interrupt >= 0.22 的比例。",
        "unit": "0 到 1",
        "aggregation": "患者级帧比例",
        "note": "浆膜线中断代理在多帧中的一致性。",
    },
    {
        "group": "growth_watch",
        "feature": "bt_v2_max_outward_depth",
        "input": "病灶 mask 和胃腔 mask。",
        "formula": "对胃腔 SDF = lumen 外部距离 - lumen 内部距离，在所有病灶像素内取最大值；正值表示部分病灶位于胃腔外，若全部位于腔内则可为负。",
        "unit": "px",
        "aggregation": "有效帧按患者取 median",
        "note": "当前 LASSO 出现方向反转，暂不直接赋分。",
    },
    {
        "group": "growth_watch",
        "feature": "bt_v2_max_outward_depth__max",
        "input": "每帧 bt_v2_max_outward_depth。",
        "formula": "患者所有有效帧的最大值。",
        "unit": "px",
        "aggregation": "患者级 max",
        "note": "比 median 更容易发现少数突破帧，但也更容易受异常帧影响。",
    },
    {
        "group": "growth_watch",
        "feature": "growth_outward_protrusion_ratio",
        "input": "病灶外轮廓径向距离 d。",
        "formula": "d 与 11 点环形移动平均 baseline 的正向差值 / baseline 均值，再对轮廓点求均值。",
        "unit": "无量纲",
        "aggregation": "有效帧按患者取 median",
        "note": "描述相对自身平滑轮廓的局部外凸，不等同于真实浆膜突破。",
    },
    {
        "group": "growth_watch",
        "feature": "growth_outward_protrusion_ratio__max",
        "input": "每帧 growth_outward_protrusion_ratio。",
        "formula": "患者所有有效帧的最大值。",
        "unit": "无量纲",
        "aggregation": "患者级 max",
        "note": "局部外凸观察项，前瞻和外部稳定性仍不足。",
    },
    {
        "group": "markers",
        "feature": "cea_value",
        "input": "原始临床表中的 CEA 数值。",
        "formula": "直接读取，不在本特征包中重新标准化或截断。",
        "unit": "沿用临床原始单位",
        "aggregation": "患者级临床字段",
        "note": "缺失值由 LASSO 管线在训练集拟合 median 后插补。",
    },
    {
        "group": "markers",
        "feature": "cea_binary",
        "input": "原始临床表中的 CEA 二值阳性字段。",
        "formula": "沿用临床数据表的 0/1 标记；本脚本不重新定义阳性阈值。",
        "unit": "0 或 1",
        "aggregation": "患者级临床字段",
        "note": "具体阈值和单位需回查原始临床数据字典。",
    },
]

METHOD_SECTIONS_ZH = [
    {
        "title": "0. 从原始帧到患者级 feature pack",
        "summary": "所有影像特征先在单帧计算，再按患者聚合；临床字段和影像字段最后按 patient_id 合并。",
        "steps": [
            "读取既有 anatomic frame CSV，获得 patient_id、image_path、预测病灶 mask 路径和胃腔框。",
            "解析图像和 mask；mask 使用二值阈值 >127。无法解析的帧标记为无效，不参与有效帧聚合。",
            "对每个有效帧分别计算 morphology、margin、growth 和 wall 特征。",
            "形态、边界、生长和胃壁帧表按 patient_id 聚合：默认保留 median、max、P90 和帧数；最终 pack 按 feature group 选择字段。",
            "把临床长径、厚径、CEA、分割几何和标签合并进患者表，并生成 eval_split。",
        ],
        "fields": "患者级 feature pack 共有 37 个可筛查字段，另有 label、patient_id、eval_split、n_features_present 等管理字段。",
        "risk": "病理 T 是结局 GT，不等于任何一个影像特征。当前胃壁字段没有完整的人工五层胃壁真值。",
        "sources": [
            ("特征包构建", "../../../../scripts/build_gc_us_tscore_feature_pack_v1.py"),
            ("形态共享库", "../../../../scripts/gc_us_contour_features.py"),
        ],
    },
    {
        "title": "1. 大小、临床和分割几何",
        "summary": "这一组是覆盖率最高的基础变量，主要表达病灶负荷和 mask 的粗几何大小。",
        "steps": [
            "tumor_length_cm 和 tumor_thickness_cm 直接来自临床患者表，不由当前 mask 重新测量。",
            "size_max_diameter_cm = max(长径, 厚径)；size_thickness_length_ratio = 厚径 / max(长径, 0.1)。",
            "seg_short_axis_ratio 来自旧版 mask 外接框：短边 / max(图像宽, 图像高)，不是短轴除以长轴。",
            "morph_area_px 和 morph_perimeter_px 来自最大外轮廓的 contourArea 和 arcLength。",
            "seg_irregularity = log(1 + P^2/A)，使用像素边界数和 mask 面积，作为控制变量。",
        ],
        "fields": "tumor_length_cm、tumor_thickness_cm、size_max_diameter_cm、size_thickness_length_ratio、seg_short_axis_ratio、morph_area_px、morph_perimeter_px、seg_irregularity。",
        "risk": "最大径、长径、厚径、面积、周长彼此共线；不能把它们同时解释成多个独立生物学机制。",
        "sources": [
            ("临床字段提取", "../../../../scripts/extract_gc_us_clinical_cohort_features_v1.py"),
            ("旧版分割几何", "../../../../scripts/extract_lumen_lesion_tstaging_features.py"),
        ],
    },
    {
        "title": "2. 轮廓形态和 NRL",
        "summary": "morph 通道只看预测病灶 mask 的轮廓几何，不直接使用灰度。",
        "steps": [
            "提取最大外轮廓，计算面积、周长、凸包面积和圆形度。",
            "将闭合轮廓按弧长重采样为 256 点，以轮廓质心为中心得到径向距离 d，并归一化为 NRL。",
            "对 NRL 做 7 点环形平滑，计算 roughness、局部峰和峰锐度。",
            "对去均值 NRL 做 rFFT，频率 1 到 3 为低频整体形状，4 到 12 为分叶，13 到 30 为细小起伏，非常高频不进入核心。",
            "患者层面通常取有效帧 median；morph_peak_sharpness_max 在帧内先取轮廓峰最大值。",
        ],
        "fields": "morph_circularity、morph_solidity、morph_concavity_ratio、morph_nrl_roughness、morph_peak_sharpness_max。",
        "risk": "峰锐度、solidity 和 concavity 可能重复表达同一轮廓现象，并且受分割毛刺影响。",
        "sources": [
            ("轮廓公式", "../../../../scripts/gc_us_contour_features.py"),
            ("形态提取入口", "../../../../scripts/extract_gc_us_morphology_features_v1.py"),
        ],
    },
    {
        "title": "3. margin 和毛刺综合指数",
        "summary": "margin 通道同时使用 mask 形状和灰度图边界证据，设计目标是减少 mask 不精确造成的假毛刺。",
        "steps": [
            "在 mask 周围建立 soft boundary band，半宽约为等效半径的 4%，限制在 3 到 10 px。",
            "BoF 在 0.90、1.05、1.20、1.35 倍等效半径圆周上采样 128 点，对灰度信号做频谱分析。",
            "NRG 是 soft band 梯度方向与径向方向的余弦均值；MI 是 band 梯度均值相对全图梯度 P90 的归一化值；contrast 是内 rim 减外 rim 的灰度差。",
            "shape 分支使用 15 点强平滑 NRL，计算 solidity、needle-like 高频/低频比例、mid/high Fourier 能量和 lobulation。",
            "margin_spic_robust 用 FD high、1-solidity、BoF high、needle-like 和 BoF peakiness 加权；margin_clear_robust 用 NRG、contrast 和 MI 加权。",
        ],
        "fields": "margin_spic_robust、margin_shape_solidity、margin_shape_fd_high、margin_bof_high_mean、margin_clear_robust。",
        "risk": "BoF 和灰度梯度会受 speckle、增益和边界定位影响；margin_clear_robust 目前是弱通道，不应直接解释为临床边界清晰度 GT。",
        "sources": [
            ("margin 计算公式", "../../../../scripts/gc_us_contour_features.py"),
            ("margin 提取入口", "../../../../scripts/extract_gc_us_margin_features_v1.py"),
        ],
    },
    {
        "title": "4. wall v1：基于 SDF 的胃壁深度软代理",
        "summary": "wall v1 把胃腔 mask 当作起点，以 SDF 估计病灶相对胃腔的外向深度。",
        "steps": [
            "计算 lumen SDF = lumen 外部距离 - lumen 内部距离；病灶像素上的正值表示位于胃腔外侧。",
            "壁厚优先取 outer wall mask 内正 SDF 的 P75；无 outer mask 时取健康 shell 2 到 60 px 内正 SDF 的 P80，最后限制在 10 到 140 px。",
            "将病灶 SDF 除以估计壁厚，得到 depth_frac；对正值计算 P50、P90 和最大值。",
            "wall_serosa_interrupt 有 outer mask 时计算病灶覆盖膨胀 outer band 的比例，没有 outer mask 时使用 depth_frac >=1.15 的比例。",
        ],
        "fields": "wall_depth_frac_p90、wall_serosa_interrupt。",
        "risk": "outer wall 在部分数据中不是人工浆膜线；因此 wall v1 是深度和浆膜中断代理，不是 EUS 五层组织学 GT。",
        "sources": [
            ("wall v1 公式", "../../../../scripts/gc_us_wall_layer_features.py"),
            ("wall v1 提取入口", "../../../../scripts/extract_gc_us_wall_layer_features_v1.py"),
        ],
    },
    {
        "title": "5. wall v2：沿最深接触方向的 ContactGeom 代理",
        "summary": "wall v2 不把 lesion-adjacent outer mask 当作浆膜，而是从胃腔轮廓和局部壁厚合成浆膜点。",
        "steps": [
            "把胃腔轮廓重采样为 96 点，计算从胃腔指向外侧的法线。",
            "用 outer mask 或健康 shell 估计每条法线上的胃壁厚度，并限制在 12 到 120 px。",
            "合成 serosa = lumen_point + outward_normal x wall_thickness。",
            "从合成浆膜向内搜索病灶，remain 取最近病灶距离和首次沿法线命中距离的较小值。",
            "选择 remain 最小的深部点，在其两侧各 8 个轮廓点形成 sector，计算 penetration ratio 的 P90。",
            "serosa_proxy 综合 remain、overshoot、penetration；composite 再加入深部和健康方向的 echo transition loss。",
        ],
        "fields": "wall_v2_pen_ratio_sector、wall_v2_composite、wall_v2_remain_px、wall_v2_serosa_proxy、wall_fuse_serosa_remain。",
        "risk": "计算方向是沿最深接触方向，但 serosa 是合成的。wall_fuse_serosa_remain 还进行了全队列 rank normalization，不具有物理单位。",
        "sources": [
            ("ContactGeom v2 公式", "../../../../scripts/gc_us_wall_layer_features.py"),
            ("axis v2 提取入口", "../../../../scripts/extract_gc_us_wall_layer_axis_v2.py"),
        ],
    },
    {
        "title": "6. 多帧 dynamics：典型帧、极端帧和一致性",
        "summary": "dynamics 不重新生成图像特征，而是从已有 frame-level CSV 统计患者内的时间或切面一致性。",
        "steps": [
            "每个特征都可生成 median、max、std、IQR、max_minus_median、n。",
            "frac_high = 满足固定高阈值的有效帧数 / 有效帧总数；frac_low 同理。",
            "当前阈值包括 peak sharpness 0.35、spiculation 0.35、BT depth 8 px、outward protrusion 0.25、wall depth P90 0.85、serosa interrupt 0.22、remain 4 px。",
            "dyn_invasion_agree 是可用 high/low consistency fractions 的均值。",
        ],
        "fields": "dyn_invasion_agree、morph_peak_sharpness_max__frac_high、margin_spic_robust__frac_high、bt_v2_max_outward_depth__frac_high、wall_v2_remain_px__frac_low、wall_serosa_interrupt__frac_high。",
        "risk": "不同特征的阈值来自当前探索性设计，不是临床共识切点；缺少有效帧时 coverage 会下降。",
        "sources": [
            ("dynamics 聚合公式", "../../../../scripts/extract_gc_us_multiframe_dynamics_v1.py"),
        ],
    },
    {
        "title": "7. growth 和 breakthrough 观察项",
        "summary": "growth v2 同时描述病灶相对胃腔的外向距离和病灶自身轮廓的局部外凸。",
        "steps": [
            "bt_v2_max_outward_depth：在 lumen SDF 上对病灶像素取最大值；正值为部分病灶越过胃腔外侧，负值表示仍在腔内。",
            "bt_v2_max_outward_depth__max：患者所有有效帧的最大突破深度。",
            "growth_outward_protrusion_ratio：病灶径向距离 d 与 11 点环形移动平均 baseline 比较，只累计正向差值，再除以 baseline 均值并对轮廓点取均值。",
            "growth_outward_protrusion_ratio__max：患者所有有效帧的最大局部外凸比例。",
        ],
        "fields": "bt_v2_max_outward_depth、bt_v2_max_outward_depth__max、growth_outward_protrusion_ratio、growth_outward_protrusion_ratio__max。",
        "risk": "breakthrough 的检测和方向仍在 redesign；max 聚合容易被异常帧放大，当前只作为 watch feature。",
        "sources": [
            ("growth 公式", "../../../../scripts/gc_us_contour_features.py"),
            ("growth 提取入口", "../../../../scripts/extract_gc_us_growth_features_v1.py"),
        ],
    },
    {
        "title": "8. 临床标志物和统计评价",
        "summary": "CEA 是临床字段，不和图像灰度混合计算；LASSO 只用于筛查，不把系数当作显著性 p 值。",
        "steps": [
            "cea_value 直接读取原始临床表；cea_binary 沿用原始 0/1 标记，本特征包不重新设定阳性阈值。",
            "LASSO 在训练集用 median imputation 和 StandardScaler 预处理，使用 L1 logistic regression，C 由 5-fold CV 选择。",
            "Bootstrap 80 次，每次固定 CV 选出的 C，记录特征非零比例作为 stability frequency。",
            "Spearman rho 和 Kruskal q 是训练集单变量关联；q 值用 Benjamini-Hochberg 校正。",
            "模型评测同时报告全队列插补结果和共同 complete-case 结果，避免把 coverage 下降误判成泛化下降。",
        ],
        "fields": "cea_value、cea_binary，以及 LASSO coefficient、stability、Spearman q、Kruskal q 等统计输出。",
        "risk": "LASSO 选择受共线性影响，归零不代表无关联；符号反转通常提示相关变量、编码方向或代理定义需要复核。",
        "sources": [
            ("clinical 字段", "../../../../scripts/extract_gc_us_clinical_cohort_features_v1.py"),
            ("LASSO 和 3D 评价", "../../../../scripts/analyze_gc_us_tscore_latest_lasso_3d_v1.py"),
        ],
    },
]


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def fmt(value: object, column: str = "") -> str:
    if value is None or pd.isna(value):
        return "-"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        value = float(value)
        if any(t in column.lower() for t in ("p", "q")) and 0 < abs(value) < 0.01:
            return f"{value:.2e}"
        if any(
            t in column.lower()
            for t in ("auc", "qwk", "acc", "rho", "ari", "nmi", "coverage", "freq", "silhouette")
        ):
            return f"{value:.3f}"
        return f"{value:.3f}"
    return str(value)


def zh_table(frame: pd.DataFrame, columns: list[str], table_id: str | None = None) -> str:
    cols = [c for c in columns if c in frame.columns]
    attr = f' id="{esc(table_id)}"' if table_id else ""
    out = [f'<div class="table-wrap"><table{attr}><thead><tr>']
    labels = {
        "model": "模型",
        "train": "训练集",
        "val": "验证集",
        "test_prospective": "前瞻测试集",
        "test_external": "外部测试集",
        "mean_heldout": "平均留出",
        "n": "N",
        "split": "数据集",
        "auc_T3plus": "T3+ AUC",
        "qwk_4class": "四分类 QWK",
        "auc_4class_ovr_macro": "四分类 OvR AUC",
        "auc_T1vsT2": "T1 对 T2 AUC",
        "auc_T2vsT3": "T2 对 T3 AUC",
        "auc_T3vsT4": "T3 对 T4+ AUC",
        "feature": "特征",
        "feature_group": "特征组",
        "lasso_coef": "LASSO 系数",
        "stability_freq": "Bootstrap 稳定性",
        "spearman_rho": "Spearman rho",
        "spearman_q": "Spearman q",
        "kruskal_q": "Kruskal q",
        "train_coverage": "训练集覆盖率",
        "triplet_id": "三元组",
        "labels_zh": "三条轴（中文）",
        "labels": "三条轴（英文）",
        "family": "提分期家族",
        "n_all": "可用 N",
        "n_train": "训练 N",
        "auc_T3plus_train": "T3+ AUC 训练",
        "auc_T3plus_val": "T3+ AUC 验证",
        "auc_T3plus_prospective": "T3+ AUC 前瞻",
        "auc_T3plus_external": "T3+ AUC 外部",
        "delta_ext_vs_length": "外部 Δ vs 长径",
        "qwk_4class_external": "四分类 QWK 外部",
        "auc_T2vsT3_external": "T2–T3 AUC 外部",
        "auc_T1vsT2_external": "T1–T2 AUC 外部",
        "auc_T3vsT4_external": "T3–T4+ AUC 外部",
        "rho_f1": "ρ 轴1",
        "rho_f2": "ρ 轴2",
        "rho_f3": "ρ 轴3",
        "best_view_elev": "最佳仰角",
        "best_view_azim": "最佳方位角",
        "train_kmeans_ari": "训练 KMeans ARI（对照）",
        "test_prospective_kmeans_ari": "前瞻 KMeans ARI（对照）",
        "test_external_kmeans_ari": "外部 KMeans ARI（对照）",
        "train_stage_silhouette_3d": "训练期分期 silhouette",
    }
    for c in cols:
        out.append(f"<th>{esc(labels.get(c, c))}</th>")
    out.append("</tr></thead><tbody>")
    for _, row in frame.iterrows():
        out.append("<tr>")
        for c in cols:
            value = row[c]
            cls = ""
            if isinstance(value, (float, np.floating)) and np.isfinite(value):
                cls = ' class="negative"' if value < 0 else ""
            out.append(f"<td{cls}>{esc(fmt(value, c))}</td>")
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def metric_card(title: str, value: str, note: str) -> str:
    return (
        '<div class="metric-card">'
        f"<div class=\"metric-title\">{esc(title)}</div>"
        f"<div class=\"metric-value\">{esc(value)}</div>"
        f"<div class=\"metric-note\">{esc(note)}</div>"
        "</div>"
    )


def image_panel(src: str, title: str, caption: str, vector: str | None = None) -> str:
    href = vector or src
    return (
        '<figure class="figure-card">'
        f'<a href="{esc(href)}" target="_blank" rel="noopener">'
        f'<img loading="lazy" src="{esc(src)}" alt="{esc(title)}"/>'
        "</a>"
        f"<figcaption><strong>{esc(title)}</strong><br/>{esc(caption)}</figcaption>"
        "</figure>"
    )


def feature_rows_html() -> str:
    rows = []
    for item in FEATURES_ZH:
        rows.append(
            "<tr>"
            f"<td><code>{esc(item['feature'])}</code></td>"
            f"<td>{esc(GROUP_ZH[item['group']])}</td>"
            f"<td>{esc(item['input'])}</td>"
            f"<td><code>{esc(item['formula'])}</code></td>"
            f"<td>{esc(item['unit'])}</td>"
            f"<td>{esc(item['aggregation'])}</td>"
            f"<td>{esc(item['note'])}</td>"
            "</tr>"
        )
    return "".join(rows)


def method_sections_html() -> str:
    blocks = []
    for section in METHOD_SECTIONS_ZH:
        steps = "".join(f"<li>{esc(step)}</li>" for step in section["steps"])
        sources = "，".join(
            f'<a href="{esc(path)}" target="_blank">{esc(label)}</a>'
            for label, path in section["sources"]
        )
        blocks.append(
            '<details class="method-card" open>'
            f"<summary>{esc(section['title'])}</summary>"
            f"<p>{esc(section['summary'])}</p>"
            f"<ol class=\"step-list\">{steps}</ol>"
            f"<p class=\"formula-box\"><strong>涉及字段：</strong>{esc(section['fields'])}</p>"
            f"<p><strong>注意事项：</strong>{esc(section['risk'])}</p>"
            f'<p class="source-links"><strong>代码来源：</strong>{sources}</p>'
            "</details>"
        )
    return "".join(blocks)


def build_html() -> str:
    root = REPORT_ROOT
    auc = pd.read_csv(root / "full_split_v1/pivot_auc_T3plus.csv")
    qwk = pd.read_csv(root / "full_split_v1/pivot_qwk_4class.csv")
    macro = pd.read_csv(root / "full_split_v1/pivot_auc_4class_ovr_macro.csv")
    detail = pd.read_csv(root / "full_split_v1/metrics_by_split.csv")
    lasso_metrics = pd.read_csv(root / "lasso_latest_v1/lasso_auc_by_split.csv")
    common_metrics = pd.read_csv(root / "lasso_latest_v1/lasso_auc_common_complete_case.csv")
    significance = pd.read_csv(root / "lasso_latest_v1/feature_significance.csv")
    stage_path = root / "lasso_latest_v1/triplet_stage_metrics.csv"
    cluster_path = root / "lasso_latest_v1/triplet_cluster_metrics.csv"
    if stage_path.exists():
        triplets = pd.read_csv(stage_path)
    else:
        triplets = pd.read_csv(cluster_path)
    with PACK_META.open(encoding="utf-8") as f:
        pack_meta = json.load(f)

    kitchen_auc = auc.loc[auc["model"] == "kitchen"].iloc[0]
    short_qwk = qwk.loc[qwk["model"] == "length+short_axis"].iloc[0]
    selected = significance[significance["selected"] == 1].sort_values(
        "lasso_abs_coef", ascending=False
    )
    zeroed = significance[significance["selected"] == 0].sort_values(
        ["spearman_q", "kruskal_q"], ascending=True
    )
    cards = "".join(
        [
            metric_card("最佳 T3+ 模型", f"{kitchen_auc['mean_heldout']:.3f}", "kitchen 平均留出 AUC"),
            metric_card("最佳四分类 QWK", f"{short_qwk['mean_heldout']:.3f}", "长径加短轴几何"),
            metric_card("LASSO 非零特征", str(len(selected)), "37 个特征中保留的项"),
            metric_card("3D 三元组", str(len(triplets)), "按病理分期关联解读（KMeans 仅对照）"),
        ]
    )

    split_counts = pack_meta.get("n_by_split", {})
    count_text = "，".join(
        f"{SPLIT_ZH.get(k, k)} {int(v)}" for k, v in split_counts.items()
    )

    def stat_value(feature: str, column: str) -> str:
        hit = significance[significance["feature"] == feature]
        if hit.empty:
            return "-"
        return fmt(hit.iloc[0][column], column)

    full_metrics = lasso_metrics.set_index("split")
    common_metrics_index = common_metrics.set_index("split")
    lasso_interpretation = (
        '<div class="interpretation-grid">'
        '<div class="callout">'
        "<strong>1. 主信号是大小和几何。</strong>"
        f"size_max_diameter_cm 的 LASSO 系数为 {esc(stat_value('size_max_diameter_cm', 'lasso_coef'))}，"
        f"稳定性 {esc(stat_value('size_max_diameter_cm', 'stability_freq'))}；"
        f"seg_short_axis_ratio 系数为 {esc(stat_value('seg_short_axis_ratio', 'lasso_coef'))}，"
        f"稳定性 {esc(stat_value('seg_short_axis_ratio', 'stability_freq'))}。"
        "这说明模型首先利用病灶负荷和分割几何，而不是单独依赖胃壁代理。"
        "</div>"
        '<div class="callout">'
        "<strong>2. 动态和浆膜中断是补充信号。</strong>"
        f"dyn_invasion_agree 系数为 {esc(stat_value('dyn_invasion_agree', 'lasso_coef'))}，"
        f"稳定性 {esc(stat_value('dyn_invasion_agree', 'stability_freq'))}；"
        f"wall_serosa_interrupt 系数为 {esc(stat_value('wall_serosa_interrupt', 'lasso_coef'))}，"
        f"稳定性 {esc(stat_value('wall_serosa_interrupt', 'stability_freq'))}。"
        "二者在单变量和多变量中都保留，但仍不能当作真实壁层侵犯标签。"
        "</div>"
        '<div class="callout warning">'
        "<strong>3. 突破特征出现方向反转。</strong>"
        f"bt_v2_max_outward_depth 的 LASSO 系数为 {esc(stat_value('bt_v2_max_outward_depth', 'lasso_coef'))}，"
        f"而 Spearman rho 为 {esc(stat_value('bt_v2_max_outward_depth', 'spearman_rho'))}。"
        "这种单变量和多变量方向不一致，提示它和大小、腔内位置或其他突破代理存在共线性，当前不能直接赋予“越大越晚期”的临床分值。"
        "</div>"
        '<div class="callout warning">'
        "<strong>4. 评测覆盖率必须和模型性能一起看。</strong>"
        f"全队列插补的前瞻和外部 AUC 为 {esc(fmt(full_metrics.loc['test_prospective', 'auc_T3plus'], 'auc_T3plus'))} 和 {esc(fmt(full_metrics.loc['test_external', 'auc_T3plus'], 'auc_T3plus'))}；"
        f"共同 complete-case 队列为 {esc(fmt(common_metrics_index.loc['test_prospective', 'auc_T3plus'], 'auc_T3plus'))} 和 {esc(fmt(common_metrics_index.loc['test_external', 'auc_T3plus'], 'auc_T3plus'))}。"
        "前者包含更多病例但需要插补，后者病例较少但特征齐全，不能混作同一个结论。"
        "</div>"
        "</div>"
    )

    selected_table = zh_table(
        selected,
        [
            "feature",
            "feature_group",
            "lasso_coef",
            "stability_freq",
            "spearman_rho",
            "spearman_q",
            "kruskal_q",
            "train_coverage",
        ],
        "lassoTable",
    )
    zeroed_table = zh_table(
        zeroed.head(15),
        [
            "feature",
            "feature_group",
            "lasso_coef",
            "stability_freq",
            "spearman_rho",
            "spearman_q",
            "train_coverage",
        ],
    )
    feature_rows = feature_rows_html()
    method_sections = method_sections_html()
    detail_cols = [
        "model",
        "split",
        "n",
        "auc_T3plus",
        "qwk_4class",
        "auc_4class_ovr_macro",
        "auc_T1vsT2",
        "auc_T2vsT3",
        "auc_T3vsT4",
    ]
    if "auc_T3plus_external" in triplets.columns:
        triplet_cols = [
            "triplet_id",
            "family",
            "labels_zh",
            "n_all",
            "n_train",
            "auc_T3plus_train",
            "auc_T3plus_val",
            "auc_T3plus_prospective",
            "auc_T3plus_external",
            "delta_ext_vs_length",
            "qwk_4class_external",
            "auc_T2vsT3_external",
            "test_external_kmeans_ari",
        ]
    else:
        triplet_cols = [
            "triplet_id",
            "labels",
            "n_all",
            "n_train",
            "best_view_elev",
            "best_view_azim",
            "train_kmeans_ari",
            "test_prospective_kmeans_ari",
            "test_external_kmeans_ari",
            "train_stage_silhouette_3d",
        ]

    report_links = []
    for summary in sorted(REPORT_ROOT.glob("*/SUMMARY.md")):
        folder = summary.parent.name
        report_links.append(
            f'<li><a href="{esc(folder + "/SUMMARY.md")}" target="_blank">{esc(folder)}</a></li>'
        )

    gallery = []
    for _, row in triplets.iterrows():
        triplet_id = str(row["triplet_id"])
        if "narrative_zh" in row and isinstance(row["narrative_zh"], str) and row["narrative_zh"].strip():
            blurb = str(row["narrative_zh"])
        else:
            labels = str(row.get("labels_zh") or row.get("labels") or "")
            blurb = (
                f"{labels}。训练 N={int(row['n_train'])}，可用 N={int(row['n_all'])}。"
                "请以病理 T 着色图解读提分期关联；KMeans 仅作无监督对照。"
            )
        stage_cap = (
            "颜色=病理 T1→T4+（不是预测类别）。大菱形为各期三维中位点，黑线只表示中位轨迹方向；"
            "重叠大时仍可有单调梯度，需结合 T3+ AUC / 相邻期 AUC 判断提分期价值。"
        )
        kmeans_cap = (
            "无监督对照：仅在训练集拟合 4 类再映射到其他 split。"
            "外部 ARI≈0 说明 cluster ≠ 病理分期，不要按颜色命名为 T1–T4+。"
        )
        gallery.append(
            '<div class="triplet-block">'
            f"<h3>{esc(triplet_id)}</h3>"
            f'<p class="muted">{esc(blurb)}</p>'
            '<div class="figure-grid">'
            + image_panel(
                f"lasso_latest_v1/{triplet_id}_stage.png",
                f"{triplet_id}，病理 T 分期分布（主图）",
                stage_cap,
                f"lasso_latest_v1/{triplet_id}_stage.svg",
            )
            + image_panel(
                f"lasso_latest_v1/{triplet_id}_kmeans.png",
                f"{triplet_id}，KMeans 四分群（对照，非提分期证据）",
                kmeans_cap,
                f"lasso_latest_v1/{triplet_id}_kmeans.svg",
            )
            + "</div></div>"
        )

    report_index = "".join(report_links)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>GC-US T-score 全部结果汇总</title>
<style>
:root {{ --ink:#202124; --muted:#5f6368; --line:#d9dee5; --paper:#fff;
  --canvas:#f4f6f8; --blue:#587fa3; --red:#c66b6b; --green:#6f9e88; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--canvas); color:var(--ink);
  font-family:"Noto Sans CJK SC","Microsoft YaHei",Arial,sans-serif; line-height:1.55; }}
header {{ position:sticky; top:0; z-index:5; background:rgba(255,255,255,.97);
  border-bottom:1px solid var(--line); padding:18px max(22px, calc((100vw - 1480px)/2)); }}
h1 {{ margin:0 0 4px; font-size:25px; }}
h2 {{ margin:0 0 10px; font-size:19px; }}
h3 {{ margin:0 0 6px; font-size:15px; }}
p {{ margin:7px 0; }}
a {{ color:#245b86; text-decoration:none; }}
a:hover {{ text-decoration:underline; }}
.subtitle,.muted {{ color:var(--muted); font-size:12px; }}
nav {{ display:flex; gap:14px; flex-wrap:wrap; margin-top:12px; font-size:12px; }}
main {{ max-width:1480px; margin:0 auto; padding:20px 22px 60px; }}
section {{ background:var(--paper); border:1px solid var(--line); padding:18px; margin-bottom:16px; }}
.cards {{ display:grid; grid-template-columns:repeat(4,minmax(150px,1fr)); gap:10px; }}
.metric-card {{ border-left:4px solid var(--blue); background:#f8fafb; padding:12px; }}
.metric-title {{ color:var(--muted); font-size:11px; }}
.metric-value {{ font-size:25px; font-weight:700; margin:4px 0; }}
.metric-note {{ color:var(--muted); font-size:11px; }}
.grid-3 {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }}
.grid-2 {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }}
.figure-card {{ margin:0; border:1px solid var(--line); background:#fff; padding:7px; }}
.figure-card img {{ display:block; width:100%; height:auto; background:#fff; }}
figcaption {{ padding:7px 3px 2px; color:var(--muted); font-size:11px; }}
figcaption strong {{ color:var(--ink); font-size:12px; }}
.figure-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }}
.figure-grid .figure-card {{ min-width:0; }}
.table-wrap {{ overflow:auto; max-height:650px; border:1px solid var(--line); }}
table {{ width:100%; border-collapse:collapse; font-size:11px; white-space:nowrap; }}
th {{ position:sticky; top:0; background:#eef2f5; text-align:left; font-weight:700; }}
th,td {{ padding:7px 8px; border-bottom:1px solid #edf0f2; vertical-align:top; }}
tr:hover {{ background:#f7fafc; }}
.negative {{ color:#a33b43; }}
.callout {{ border-left:4px solid var(--green); background:#f4faf6; padding:11px 13px; font-size:13px; }}
.warning {{ border-left-color:var(--red); background:#fff7f7; }}
.links {{ columns:3; padding-left:20px; font-size:12px; }}
.triplet-block {{ border-top:1px solid var(--line); padding-top:15px; margin-top:16px; }}
.search {{ width:100%; max-width:420px; padding:8px 10px; border:1px solid var(--line); margin:6px 0 10px; font-size:12px; }}
details {{ margin-top:12px; }}
summary {{ cursor:pointer; font-weight:700; font-size:13px; }}
code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.92em; white-space:normal; }}
.feature-table {{ white-space:normal; min-width:1120px; }}
.feature-table th:nth-child(1) {{ width:190px; }}
.feature-table th:nth-child(3) {{ width:230px; }}
.feature-table th:nth-child(4) {{ width:360px; }}
.feature-table th:nth-child(7) {{ width:240px; }}
.method-card {{ border:1px solid var(--line); background:#fbfcfd; padding:12px 14px; margin-top:10px; }}
.method-card summary {{ font-size:14px; color:#1f4f72; }}
.method-card p {{ font-size:12px; }}
.step-list {{ margin:8px 0 10px 22px; padding:0; font-size:12px; }}
.step-list li {{ margin:4px 0; }}
.formula-box {{ border-left:3px solid var(--blue); background:#f2f7fb; padding:8px 10px; }}
.source-links {{ color:var(--muted); font-size:11px !important; }}
.interpretation-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }}
.interpretation-grid .callout {{ font-size:12px; }}
@media (max-width:900px) {{
  .cards,.grid-3,.grid-2,.figure-grid,.interpretation-grid {{ grid-template-columns:1fr; }}
  .links {{ columns:1; }}
  header {{ position:static; }}
}}
</style>
</head>
<body>
<header>
  <h1>GC-US T-score，全部结果汇总</h1>
  <div class="subtitle">最新特征包、全 split 评测、LASSO 筛查、三维分群和特征计算字典。生成时间 {esc(generated)}。</div>
  <nav>
    <a href="#overview">总览</a>
    <a href="#features">特征怎么算</a>
    <a href="#full-split">全 split 结果</a>
    <a href="#lasso">LASSO</a>
    <a href="#triplets">提分期 3D</a>
    <a href="#limitations">局限性</a>
    <a href="#reports">历史报告</a>
    <a href="index_en.html">English version</a>
  </nav>
</header>
<main>
<section id="overview">
  <h2>一、结果总览</h2>
  <div class="cards">{cards}</div>
  <div class="callout" style="margin-top:14px">
    <strong>当前结论：</strong>大小和分割几何仍是最稳定的主信号；多帧侵袭一致性和浆膜中断代理有补充价值。三维图显示的是连续分期梯度，不是四个清晰的无监督生物学聚类。
  </div>
  <p class="subtitle">当前特征包共 {int(pack_meta.get("n_patients", 0))} 例。数据分布：{esc(count_text)}。病理 T 分期是主要结局 GT；胃壁相关字段均为软代理，不能当作组织学 L1 到 L5 真值。</p>
</section>

<section id="features">
  <h2>二、每个特征怎么算</h2>
  <div class="callout warning">
    <strong>先看计算口径：</strong>影像特征都从预测病灶 mask、胃腔框或灰度图计算。患者表中的 morphology、margin、growth、wall 特征通常先在有效帧计算，再按患者取 median；名称带 <code>__max</code> 的字段取患者所有有效帧最大值；名称带 <code>__frac_high</code> 或 <code>__frac_low</code> 的字段是超过或低于固定阈值的帧比例。
  </div>
  <p>公式中的 <code>px</code> 是图像像素，不等于毫米；临床长径、厚径和 CEA 沿用原始临床表单位。胃壁 v2 使用合成浆膜，计算方向对齐最深接触或突破方向，但目前没有完整人工浆膜 polyline 标注。</p>
  <input class="search" placeholder="搜索特征名、计算公式或注意事项" oninput="filterTable('featureTable', this.value)"/>
  <div class="table-wrap">
    <table id="featureTable" class="feature-table">
      <thead><tr><th>字段</th><th>特征组</th><th>输入</th><th>公式或算法</th><th>单位或范围</th><th>患者级聚合</th><th>解释和风险</th></tr></thead>
      <tbody>{feature_rows}</tbody>
    </table>
  </div>
  <details>
    <summary>为什么同一现象有多个字段</summary>
    <p><strong>形态：</strong>morph 通道偏向轮廓几何和 NRL 峰，margin 通道偏向强平滑形状、灰度圆周频谱和 soft-band 梯度。</p>
    <p><strong>胃壁：</strong>wall v1 是全病灶 SDF 和外壁覆盖软代理，wall v2 是沿深部接触方向的 ContactGeom 风格代理；二者都不是真实五层胃壁标注。</p>
    <p><strong>动态：</strong>median 描述典型帧，max 描述极端帧，frac_high 或 frac_low 描述多帧一致性。深度极值不能直接等同于临床最深侵犯。</p>
  </details>
  <h3 style="margin-top:18px">按计算流程展开</h3>
  {method_sections}
</section>

<section id="full-split">
  <h2>三、全 split 模型结果</h2>
  <p>所有模型只在训练集拟合。模型之间使用 kitchen 和 pack_core 的共同 complete-case 队列，训练集为样本内结果，验证集、前瞻测试集和外部测试集为留出结果。</p>
  <div class="grid-3">
    {image_panel("full_split_v1/00_auc_T3plus_all_splits.png", "T3+ AUC", "二分类 T3+ 鉴别。")}
    {image_panel("full_split_v1/00_qwk_4class_all_splits.png", "四分类 QWK", "T1 到 T4+ 的序数一致性。")}
    {image_panel("full_split_v1/00_adjacent_auc_by_split.png", "相邻分期 AUC", "T1 对 T2、T2 对 T3、T3 对 T4+。")}
  </div>
  <h3 style="margin-top:18px">T3+ AUC</h3>
  {zh_table(auc, ["model", "train", "val", "test_prospective", "test_external", "mean_heldout"])}
  <h3 style="margin-top:18px">四分类 QWK</h3>
  {zh_table(qwk, ["model", "train", "val", "test_prospective", "test_external", "mean_heldout"])}
  <details><summary>四分类 OvR AUC</summary>{zh_table(macro, ["model", "train", "val", "test_prospective", "test_external", "mean_heldout"])}</details>
  <details><summary>所有模型的逐 split 细节</summary>{zh_table(detail, detail_cols, "detailTable")}</details>
</section>

<section id="lasso">
  <h2>四、最新特征 LASSO 和稳定性</h2>
  <div class="grid-2">
    {image_panel("lasso_latest_v1/00_lasso_coefficients_top18.png", "LASSO 非零系数", "红色为正系数，蓝色为负系数。", "lasso_latest_v1/00_lasso_coefficients_top18.pdf")}
    <div>
      <div class="callout warning"><strong>显著性解释：</strong>LASSO 系数不是 p 值。Bootstrap 稳定性是 80 次重采样中的保留比例。Spearman q 和 Kruskal q 是训练集单变量检验的 Benjamini-Hochberg 校正结果。</div>
      <h3>全队列插补结果</h3>
      {zh_table(lasso_metrics, ["split", "n", "auc_T3plus"])}
      <h3>共同 complete-case 结果</h3>
      {zh_table(common_metrics, ["split", "n", "auc_T3plus"])}
    </div>
  </div>
  <h3 style="margin-top:18px">LASSO 保留的非零特征</h3>
  <input class="search" placeholder="搜索 LASSO 特征" oninput="filterTable('lassoTable', this.value)"/>
  {selected_table}
  <details><summary>单变量显著但被 LASSO 归零的特征</summary>
    <p class="muted">这些字段单独和 T 分期有关，但在多变量 L1 模型中被相关字段替代，不能解读为“没有关系”。</p>
    {zeroed_table}
  </details>
  <h3 style="margin-top:18px">LASSO 结果详细解读</h3>
  {lasso_interpretation}
</section>

<section id="triplets">
  <h2>五、3D 提分期关联（病理着色为主）</h2>
  <p>这一节的目标不是“找四个好看的 cluster”，而是回答：这三条轴合在一起，能不能跟着病理 T 分期走、能不能抬 T3+ / 相邻期判别。每组保留两张图：<strong>左图（主图）按病理 T1–T4+ 着色</strong>；右图 KMeans 只作无监督对照。下表指标一律按<strong>训练集拟合、分 split 报告</strong>的提分期关联计算。</p>
  <div class="callout">
    <strong>怎么按提分期读，而不是按聚类读。</strong>
    先看病理着色是否出现 T1→T4+ 中位轨迹（黑线），再看 T3+ AUC、四分类 QWK、以及 T1–T2 / T2–T3 / T3–T4+ 相邻期 AUC。
    「含临床长径」家族通常扛起主判别；「纯影像几何+壁/动态」家族（如 L11）即使中位数单调抬升，外部 T3+ 仍可能远弱于长径基线——这时它的价值是补充壁层/动态信息，不是替代大小。
  </div>
  <div class="callout warning">外部 KMeans ARI 普遍接近 0（L11≈-0.004）。这只说明无监督四类不能复现病理分期，<strong>不能</strong>据此否定分期梯度本身。聚类失败 ≠ 与分期无关；请以病理着色图和 AUC/QWK 表为准。</div>
  <details class="method-card" open>
    <summary>如何阅读三维图与提分期指标</summary>
    <ol class="step-list">
      <li><strong>主图颜色 = 术后病理 T</strong>，不是模型预测，也不是 KMeans 类别。</li>
      <li>黑线连接各期三维中位点，用来看“提分期方向”；散点重叠大时仍可能有单调梯度。</li>
      <li><strong>T3+ AUC</strong>：三特征 logistic 只在训练集拟合，再在验证/前瞻/外部报告——这是二分类提分期的主数字。</li>
      <li><strong>Δ vs 长径</strong>：同队列长径基线外部 AUC 的差值；负得越多，说明这三条轴越依赖/弱于临床大小。</li>
      <li><strong>相邻期 AUC</strong>：看难分界面（尤其 T2–T3、T3–T4+），比“能不能聚成四团”更贴近临床提分期。</li>
      <li>KMeans / ARI 仅对照：ARI≈0 或负值 = cluster 与病理分期不一致，不要把 cluster 色当分期色。</li>
      <li>三维视角用训练集标签搜索，只为可读性，不是独立验证指标。</li>
    </ol>
  </details>
  <h3 style="margin-top:18px">三元组提分期指标（主表）</h3>
  <p class="muted">优先比较：外部 T3+ AUC、Δ vs 长径、外部 QWK、T2–T3 外部 AUC。最后一列外部 KMeans ARI 只是聚类对照。</p>
  {zh_table(triplets, triplet_cols, "tripletTable")}
  <h3 style="margin-top:18px">逐组详解</h3>
  {''.join(gallery)}
</section>

<section id="limitations">
  <h2>六、当前局限和下一步</h2>
  <div class="callout warning">
    <strong>不要把当前结果写成“已经完成临床 T 分期标准”。</strong>
    当前工作完成的是特征工程、患者级统计筛查和探索性可视化；还没有完成锁定规则、人工真值校准和正式外部验证。
  </div>
  <ul>
    <li><strong>胃壁：</strong>wall v1 和 wall v2 都是软代理；v2 的 serosa 是合成点，不是人工勾画的真实浆膜线。</li>
    <li><strong>突破：</strong>median、max 和 SDF 方向仍可能受异常帧、胃腔框和 mask 偏差影响，当前只保留为 watch feature。</li>
    <li><strong>共线性：</strong>长径、厚径、最大径、面积、周长和短轴几何高度相关，LASSO 归零不能解释为生物学无效。</li>
    <li><strong>覆盖率：</strong>完整 feature pack 的 complete-case 前瞻测试集只有 41 例，外部测试集 170 例；所有结论需要给出 N 和缺失处理方式。</li>
    <li><strong>统计显著性：</strong>Spearman/Kruskal q 是单变量筛查，LASSO 系数没有传统回归 p 值，不能当作因果效应。</li>
    <li><strong>下一步：</strong>优先做真实胃壁和局部外凸的人工作业校准，再锁定离散 T-score 规则，最后进行分层外部验证和人工阅片一致性研究。</li>
  </ul>
</section>

<section id="reports">
  <h2>七、详细报告和原始文件</h2>
  <ul class="links">{report_index}</ul>
  <p>
    <a href="index_en.html" target="_blank">英文版汇总</a> |
    <a href="full_split_v1/SUMMARY.md" target="_blank">全 split 报告</a> |
    <a href="lasso_latest_v1/SUMMARY.md" target="_blank">LASSO 报告</a> |
    <a href="../../../data/gc_us_tscore_features_v1/feature_pack_v1/FEATURE_PACK.md" target="_blank">特征包说明</a> |
    <a href="../../../../scripts/analyze_gc_us_tscore_latest_lasso_3d_v1.py" target="_blank">LASSO 和 3D 重跑脚本</a>
  </p>
</section>
</main>
<script>
function filterTable(id, query) {{
  const q = query.toLowerCase();
  const table = document.getElementById(id);
  if (!table) return;
  for (const row of table.tBodies[0].rows) {{
    row.style.display = row.innerText.toLowerCase().includes(q) ? "" : "none";
  }}
}}
</script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build_html(), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "bytes": args.out.stat().st_size}, indent=2))


if __name__ == "__main__":
    main()

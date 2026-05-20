# 外省整理「湖北窦」误标修复说明

## 问题

`外省整理.zip` 中子目录 **湖北窦** 被映射为 **湖北中西医结合医院**，但帧头 OCR 显示：

- **214/216** 张图为 `LanZhou 504 Hospital`（兰州中核五〇四医院）
- **0** 张图出现「湖北」「中西医结合」等字样
- 临床表 `hbd1`–`hbd67` 与图像命名一致，说明 **病例编号可信**，但 **医院归属错误**

典型样例：`hbd1-3.jpg` 帧头为 `LanZhou 504 Hospital`，与文件夹名矛盾。

## 根因

`scripts/migrate_center_folder_names.py` 将 zip 内 **湖北窦**（贡献者/打包标签）误当作 **湖北省中西医结合医院**。

## 修复（2026-05-20）

| 项目 | 旧 | 新 |
| --- | --- | --- |
| 解压目录 | `data/extracted_external_province_review/湖北中西医结合医院` | `.../中核五〇四医院` |
| 正式数据集 | `dataset/external/湖北中西医结合医院` | `dataset/external/中核五〇四医院` |
| 临床表 | `湖北胃癌临床资料模板.xlsx` | `中核五〇四医院胃癌临床资料模板.xlsx` |
| center_id | `external_hubei_tcm`（废弃） | `external_cnnc_504`（胃癌直接手术 newzip） |
| split | `test_external_newzip` 中 source | `ext/newzip/中核五〇四医院` |

附加修复：`safe_slug` 现保留 Unicode **〇**（U+3007），避免 sample_id 变成 `中核五_四医院`。

## 审计产物（2026-05-20 复跑）

- `dataset/tables/external_hospital_overlay_audit.csv` — 全 newzip 原图 552 张，**mismatch=0**
- `scripts/audit_external_center_hospital_overlay.py` — 可复跑全中心帧头 OCR
- `scripts/fix_mislabeled_hubei_to_cnnc504.py` — 一键重分类 + 重建 manifest/split

复跑后 `中核五〇四医院` 目录下 **214/216** 张 JPG 帧头 OCR 含 `LanZhou 504 Hospital`；**0** 张出现「湖北」「中西医结合」。

## 未匹配 OCR 的 2 张图

- `hbd16-1.bmp`：帧头文字极少，仍保留在 manifest，建议人工复核
- `hbd4-3.png`：OCR 几乎为空，建议人工复核

## 后续使用注意

- **不要**再将该批数据记为湖北省外部中心
- 胃溃疡视频任务仍在 `data/中核五〇四医院/`，与本次 **胃癌直接手术** 图像 cohort 分开管理
- 重新训练/评估前请使用更新后的 `test_external_newzip_clinical.csv`

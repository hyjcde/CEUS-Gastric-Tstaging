Grad-CAM 测试集筛图包
====================
生成时间: 2026-05-24T07:35:27.978266+00:00

【医生用法 — 推荐】
  1. 解压对应 zip（外部 / 前瞻 分开筛，标注互不影响）
  2. 进入文件夹，双击 gradcam_screening.html
  3. 只需标记质量差的图：按 X 或点「标记剔除」
  4. 图质量好：直接翻下一张，不用点保留
  5. 筛完后点「导出剔除 CSV」，发回算法组

【每个 slim zip 内含】
  - gradcam_screening.html  （离线筛图网页，双击即用）
  - gradcam_results.csv     （预测结果与 panel 路径）
  - panels/.../*_panel.png  （Grad-CAM 可视化大图）

【合并包 gradcam_test_clinical_bundle.zip】
  含外部 + 前瞻两个文件夹 + 统一 gradcam_screening.html + 本说明
  若两个数据集一起筛，解压后打开根目录 gradcam_screening.html

【样本量说明】
  - test_external: 2430 张（含内部前瞻 253 张重复行，纯外部 holdout 2177 张）
  - test_prospective: 2285 张（2025 前瞻全量 crop_ui，含临床；磁盘共 2430，缺临床 145）
  - test holdout 253 张仅用于模型 benchmark，临床筛图请用前瞻全量包
  - 统一 HTML = 外部 holdout 2177 + 前瞻全量 2285（可能有 filename 重叠）

Split: test_prospective
  gradcam_results 行数: 2285
  panel PNG 文件数: 2285
  打包 panel 数: 2285
  正确 / 分错: 1326 / 959
  pack_mode: slim

ZIP 文件:
  - gradcam_test_prospective_slim.zip (488.3 MB)
  - gradcam_test_clinical_bundle.zip (18559.9 MB) [合并包]

# segmentation

这里存放正式的分割模型实验。

当前分割是 Stage 1 的核心组成部分，不只是辅助可视化。

当前除了既有分割路线外，也支持把 `SLab-Medical-Segmentation` 作为 2D 分割后端接入。

建议流程：

1. 用 `scripts/prepare_sms_gastric_2d_dataset.py` 整理数据
2. 用 `scripts/run_sms_train.py` 启动训练
3. 用 `scripts/run_sms_inference.py` 回收预测结果并复用当前仓库的评估与 overlay 脚本

import os
import json
import pandas as pd
import torch  # 引入 torch 进行显卡检测
from autogluon.tabular import TabularDataset, TabularPredictor
from sklearn.model_selection import train_test_split

# ================= 配置区域 =================
# 1. 数据路径
DATASET_PATH = "processed_dataset/autogluon_dataset.csv"
MAPPING_PATH = "processed_dataset/label_mapping.json"
MODEL_SAVE_PATH = "autogluon_gesture_model"

# 2. 训练配置
LABEL_COLUMN = 'label'
TIME_LIMIT = None
PRESET = 'high_quality'
# ===========================================

def train_gesture_model():
    print(">>> 1. 加载数据...")
    if not os.path.exists(DATASET_PATH):
        print(f"错误: 找不到数据集 {DATASET_PATH}！")
        return

    data = TabularDataset(DATASET_PATH)
    print(f"数据加载成功，形状: {data.shape}")

    if os.path.exists(MAPPING_PATH):
        with open(MAPPING_PATH, 'r', encoding='utf-8') as f:
            mapping = json.load(f)
            id_to_name = {v: k for k, v in mapping.items()}
            print(f"加载了 {len(id_to_name)} 个手势类别。")
    else:
        id_to_name = {}

    train_data, test_data = train_test_split(data, test_size=0.2, random_state=42)
    print(f"训练集: {len(train_data)}, 测试集: {len(test_data)}")

    # --- 显式 GPU 检测逻辑 ---
    # 这比 AutoGluon 的 'auto' 更稳健，能避免报错
    if torch.cuda.is_available():
        gpu_count = torch.cuda.device_count()
        print(f"\n✅ 检测到 {gpu_count} 个 GPU，将启用加速！")
        num_gpus_arg = 1  # 分配给 AutoGluon 的 GPU 数量
    else:
        print("\n⚠️ 未检测到 GPU 或 PyTorch GPU 版本未安装。")
        print("   将自动切换为 CPU 模式进行训练（速度较慢，但不会报错）。")
        num_gpus_arg = 0

    print(f"\n>>> 2. 开始训练 AutoGluon (GPU={num_gpus_arg})...")

    # 初始化预测器
    predictor = TabularPredictor(
        label=LABEL_COLUMN,
        path=MODEL_SAVE_PATH,
        problem_type='multiclass',
        eval_metric='accuracy'
    ).fit(
        train_data,
        time_limit=TIME_LIMIT,
        presets=PRESET,

        # --- 关键修改 1: 显式指定 GPU 数量 ---
        num_gpus=num_gpus_arg,

        # --- 关键修改 2: 解决 Windows 下 GPU 不被调用/报错的问题 ---
        # 强制使用'sequential'（顺序）策略而不是并行的 Ray。
        # 这样可以确保模型在主进程中训练，从而正确识别并使用显卡。
        ag_args_ensemble={'fold_fitting_strategy': 'sequential'},

        # 可选：如果你希望神经网络等模型必须用 GPU，可以取消下面这行的注释
        # ag_args_fit={'num_gpus': 1}
    )

    print("\n>>> 3. 评估模型...")
    performance = predictor.evaluate(test_data)
    print("评估结果:", performance)

    print("\n>>> 4. 预测演示...")
    sample_data = test_data.sample(5)
    y_true = sample_data[LABEL_COLUMN]
    sample_data_no_label = sample_data.drop(columns=[LABEL_COLUMN])
    y_pred = predictor.predict(sample_data_no_label)

    for idx, (true_id, pred_id) in enumerate(zip(y_true, y_pred)):
        true_name = id_to_name.get(true_id, str(true_id))
        pred_name = id_to_name.get(pred_id, str(pred_id))
        res = "✅" if true_id == pred_id else "❌"
        print(f"样本 {idx}: 真实[{true_name}] -> 预测[{pred_name}] {res}")

if __name__ == "__main__":
    train_gesture_model()
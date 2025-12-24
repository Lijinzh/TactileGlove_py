import os
import pandas as pd
import numpy as np
from scipy import signal
import glob
import json

# ================= 配置区域 =================
# 1. 数据路径配置
DATA_DIR = "collected_data_v2"       # 采集程序生成的原始数据根目录
OUTPUT_DIR = "processed_dataset"     # 处理后数据的保存目录

# 2. 数据处理参数
TARGET_LENGTH = 100                  # 将所有样本统一重采样到 100 个时间步 (约 2秒)
RAW_TOTAL_SENSORS = 24               # 原始数据的总列数

# 3. 传感器通道筛选与排序 (根据您的硬件映射)
SORTED_CHANNELS = [
    # 拇指区 (Thumb)
    6, 7, 9, 10,
    # 食指区 (Index)
    1, 8, 5,
    # 中指区 (Middle)
    2, 4, 3,
    # 无名指区 (Ring)
    14, 19, 15,
    # 小指区 (Pinky)
    20, 16,
    # 手腕区 (Wrist)
    12, 13, 11, 23, 24
]

# 4. 手势列表 (必须与采集程序完全一致，用于生成 ID)
GESTURE_LIST = [
    "Wrist abduction", "Wrist adduction", "Wrist flexion", "Wrist extension",
    "Fist (thumbs in)", "Open paper", "Close paper",
    "Thumbs and index", "Thumbs and middle", "Thumbs and ring", "Thumbs and pinky",
    "Middle and ring",
    "Letter A", "Letter B", "Letter C", "Letter D", "Letter E",
    "Letter F", "Letter G", "Letter H", "Letter I", "Letter J",
    "Letter K", "Letter L", "Letter M", "Letter N", "Letter O",
    "Letter P", "Letter Q", "Letter R", "Letter S", "Letter T",
    "Letter U", "Letter V", "Letter W", "Letter X", "Letter Y",
    "Letter Z",
    "Number 0", "Number 1", "Number 2", "Number 3", "Number 4",
    "Number 5", "Number 6", "Number 7", "Number 8", "Number 9"
]

# 生成映射字典: {"Wrist_abduction": 0, "Wrist_adduction": 1, ...}
# 注意：采集程序保存文件名时将空格替换为了下划线，这里也要保持一致
GESTURE_TO_ID = {name.replace(" ", "_"): i for i, name in enumerate(GESTURE_LIST)}

# ===========================================

def parse_label_from_filename(filename):
    """
    从文件名中解析手势名称，并转换为数字 ID。
    """
    base = os.path.splitext(filename)[0]

    # 文件名格式: 01_Wrist_abduction_rep01_...
    if "_rep" in base:
        name_part = base.split("_rep")[0] # -> 01_Wrist_abduction

        # 去掉开头的数字编号 "01_"
        first_underscore = name_part.find("_")
        if first_underscore != -1:
            label_str = name_part[first_underscore+1:] # -> Wrist_abduction

            # --- 关键修改：将字符串映射为数字 ID ---
            if label_str in GESTURE_TO_ID:
                return GESTURE_TO_ID[label_str]
            else:
                print(f"警告: 未知标签 '{label_str}' (文件: {filename})")
                return -1

    return -1

def process_data_for_autogluon():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    search_path = os.path.join(DATA_DIR, "**", "*.csv")
    csv_files = glob.glob(search_path, recursive=True)

    if not csv_files:
        print(f"错误: 在 {DATA_DIR} 下未找到任何 CSV 文件。")
        return

    print(f"扫描到 {len(csv_files)} 个数据文件，开始处理...")

    # 保存映射表到 JSON，方便后续查阅
    mapping_path = os.path.join(OUTPUT_DIR, "label_mapping.json")
    with open(mapping_path, 'w', encoding='utf-8') as f:
        json.dump(GESTURE_TO_ID, f, indent=4, ensure_ascii=False)
    print(f"标签映射表已保存至: {mapping_path}")

    processed_samples = []
    processed_labels = []
    valid_count = 0

    for file_path in csv_files:
        try:
            df = pd.read_csv(file_path)
            if df.empty: continue

            filename = os.path.basename(file_path)

            # 获取数字标签 ID
            label_id = parse_label_from_filename(filename)

            if label_id == -1:
                continue # 跳过无法识别标签的文件

            # 提取指定通道数据
            target_cols = [f"dR_ratio_{i}" for i in SORTED_CHANNELS]
            if not all(col in df.columns for col in target_cols):
                continue

            data_matrix = df[target_cols].values
            data_matrix = np.nan_to_num(data_matrix)

            if len(data_matrix) < 10: continue

            # 重采样
            resampled_data = signal.resample(data_matrix, TARGET_LENGTH)

            processed_samples.append(resampled_data)
            processed_labels.append(label_id)
            valid_count += 1

        except Exception as e:
            print(f"处理出错: {file_path}, {e}")

    if valid_count == 0:
        print("未生成有效数据。")
        return

    print(f"成功处理 {valid_count} 个样本。")

    # 转换为表格格式
    X = np.array(processed_samples) # (N, 100, 20)
    y = np.array(processed_labels)  # (N,)

    N, T, C = X.shape
    X_flat = X.reshape(N, -1)

    feature_names = []
    for t in range(T):
        for ch_idx in SORTED_CHANNELS:
            feature_names.append(f"t{t}_ch{ch_idx}")

    df_final = pd.DataFrame(X_flat, columns=feature_names)

    # --- 关键修改：最后一列现在是数字 ID ---
    df_final['label'] = y

    csv_save_path = os.path.join(OUTPUT_DIR, "autogluon_dataset.csv")
    df_final.to_csv(csv_save_path, index=False)

    print("-" * 40)
    print(f"处理完成！数据集已保存至: {csv_save_path}")
    print(f"标签映射参考: {mapping_path}")
    print("-" * 40)

if __name__ == "__main__":
    process_data_for_autogluon()
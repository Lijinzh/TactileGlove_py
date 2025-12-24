from autogluon.tabular import TabularDataset, TabularPredictor

# 读取数据
data = TabularDataset('label/str3.csv')

# 假设标签列名为 'label'，请根据实际情况修改
label_column = 'label'

# 使用所有数据作为训练集
train_data = data

# 初始化并训练模型
predictor = TabularPredictor(label=label_column, problem_type='multiclass').fit(train_data)

print("模型训练完成！")
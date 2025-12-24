# predict_gui.py (修改后的版本)
from PyQt5.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget, QSizePolicy
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QPixmap
from autogluon.tabular import TabularPredictor
import pandas as pd
import sys
import random  # 仅用于演示，实际使用时应替换为真实的传感器读取逻辑
from PyQt5.QtWidgets import QHBoxLayout

class ResistancePredictorUI(QWidget):
    def __init__(self, sensor_data=None):
        super().__init__()
        self.predictor = None
        self.sensor_data = sensor_data
        self.initUI()
        self.initPredictor()
        # 如果提供了传感器数据，则立即进行预测
        if sensor_data is not None:
            self.updatePrediction(sensor_data)

    def initUI(self):
        self.setWindowTitle('手语识别系统')  # 修改窗口标题
        # 主布局（水平布局）
        main_layout = QVBoxLayout(self)
        
        # 设置主布局的间距和边距
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # 图片和字母横向布局
        img_letter_layout = QHBoxLayout()
        img_letter_layout.setSpacing(10)
        main_layout.addLayout(img_letter_layout)

        # 图片显示标签
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        # 设置图片标签的尺寸策略，使其可以扩展
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        img_letter_layout.addWidget(self.image_label)

        # 字母/汉字标签
        self.letter_label = QLabel('手语示意图')
        self.letter_label.setAlignment(Qt.AlignCenter)
        # 设置字母标签的尺寸策略，使其可以扩展
        self.letter_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.letter_label.setStyleSheet('font-size: 200px; color: #2d8cf0; border: 1px solid #eee;')
        img_letter_layout.addWidget(self.letter_label)

        # 预测结果标签
        self.result_label = QLabel('等待预测...')
        self.result_label.setAlignment(Qt.AlignCenter)
        self.result_label.setStyleSheet('font-size: 24px;')
        # 设置结果标签的尺寸策略
        self.result_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        main_layout.addWidget(self.result_label)

        # 初始显示0.png和汉字
        self.updateImage(0)
        self.updateLetter(0)

    def initPredictor(self):
        """初始化AutoGluon预测器"""
        try:
            self.predictor = TabularPredictor.load('AutogluonModels/ag-20250916_140451')
        except Exception as e:
            print(f"预测器加载失败: {str(e)}")
            self.result_label.setText(f'预测器加载失败: {str(e)}')

    def updateImage(self, label):
        """更新显示的图片"""
        try:
            pixmap = QPixmap(f"picture/{label}.png")
            # 修改图片缩放方式，使其适应标签大小
            scaled_pixmap = pixmap.scaled(
                self.image_label.width(), 
                self.image_label.height(), 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)
        except Exception as e:
            print(f"无法加载图片 {label}.png: {str(e)}")
            self.image_label.setText(f"无法加载图片 {label}.png")

    def updateLetter(self, label):
        """更新显示的字母或汉字"""
        # 根据窗口大小动态调整字体大小
        font_size = max(40, min(120, self.width() // 10))
        
        if label == 0:
            self.letter_label.setText(f'<div style="font-size:{font_size}px;font-weight:bold;font-family:SimHei;text-align:center;margin:0;padding:0;line-height:1;">手语<br>示意图</div>')
            self.letter_label.setTextFormat(Qt.RichText)
        elif 1 <= label <= 26:
            self.letter_label.setText(f'<span style="font-size:{font_size}px;font-weight:bold;font-family:SimHei;margin:0;padding:0;line-height:1;">{chr(64 + label)}</span>')
            self.letter_label.setTextFormat(Qt.RichText)
        else:
            self.letter_label.setText(f'<span style="font-size:{font_size}px;font-weight:bold;font-family:SimHei;margin:0;padding:0;line-height:1;">未知</span>')
            self.letter_label.setTextFormat(Qt.RichText)

    def get_sensor_data(self, sensor_data=None):
        """
        获取传感器数据
        如果提供了sensor_data参数，则使用该数据
        否则使用随机数据进行演示
        """
        if sensor_data is not None:
            return sensor_data
        # 示例数据，实际使用时需要替换为真实的传感器读取逻辑
        return [-0.09446966589863,0.1725469643013276,-0.0313335189606872,0,-0.0269795971180024,0.2601927013018577,0.1143857458175417,-0.0073066890077749,0.0825216528551537,0.1237400605984516,0.0538176354841013,0.0084439831657829,0.014037015495062,0.1003766639130436,0.3869161293763697,0.2005419396416573,0,0,0.2906965875180164,0.1594957498627864,0.0038397390474919,0,0,0]

    def updatePrediction(self, sensor_data=None):
        """更新预测结果"""
        if self.predictor is None:
            self.result_label.setText('<span style="font-weight:bold;font-family:SimHei;">预测器未初始化</span>')
            self.result_label.setTextFormat(Qt.RichText)
            return

        try:
            sensor_data = self.get_sensor_data(sensor_data)
            columns = [f'Sensor_{i+1}' for i in range(24)]
            df = pd.DataFrame([sensor_data], columns=columns)
            prediction = self.predictor.predict(df)
            label = int(prediction.iloc[0])
            self.result_label.setText(f'<span style="font-weight:bold;font-family:SimHei;">当前预测结果: {label}</span>')
            self.result_label.setTextFormat(Qt.RichText)
            self.updateImage(label)
            self.updateLetter(label)
            # 保存当前标签值，用于窗口大小变化时更新显示
            self.current_label = label
            return label
        except Exception as e:
            self.result_label.setText(f'<span style="font-weight:bold;font-family:SimHei;">预测错误: {str(e)}</span>')
            self.result_label.setTextFormat(Qt.RichText)
            return None

    def resizeEvent(self, event):
        """处理窗口大小变化事件"""
        # 当窗口大小改变时，重新调整图片和文字
        super().resizeEvent(event)
        # 重新加载当前图片以适应新尺寸
        # 这里可以添加重新加载图片的逻辑
        if hasattr(self, 'current_label'):
            self.updateImage(self.current_label)
            self.updateLetter(self.current_label)


def predict_and_show(sensor_data=None):
    """
    接口函数：接收传感器数据，显示预测结果窗口
    参数:
        sensor_data: 传感器数据列表，长度为24
    返回:
        QApplication实例和窗口实例
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    window = ResistancePredictorUI(sensor_data)
    window.show()
    return app, window

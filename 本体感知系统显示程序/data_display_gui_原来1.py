# 导入所需的库

import struct  # 用于解析二进制数据
import numpy as np  # 用于数组处理
import time  # 用于时间相关功能
from collections import deque  # 用于高效队列操作
# 导入PyQt5相关组件用于GUI界面
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
                             QLabel, QVBoxLayout, QFrame, QPushButton)

from PyQt5.QtCore import Qt, QTimer  # Qt核心功能和定时器
from PyQt5.QtGui import QColor, QPalette  # Qt图形界面相关
import csv, os
import config_utils
import perception_data_processor

# 添加导入语句
from predict_gui import predict_and_show


class HighSpeedReceiver:
    """高速数据接收器类，负责从网络接收和解析数据"""

    def __init__(self):
        """初始化接收器"""
        self.buffer = bytearray()  # 创建字节缓冲区用于存储接收到的数据
        self.fps_tracker = deque(maxlen=30)  # 创建长度为30的双端队列用于追踪FPS
        self.latest_reversed_data = [0] * config_utils.TOTAL_CELLS  # 初始化24个0作为最新数据

    def receive(self, sock):
        """从socket接收数据并解析"""
        try:
            data = sock.recv(4096)  # 从socket接收最多4096字节数据
            if not data:  # 如果没有接收到数据，返回None
                return None
            self.buffer.extend(data)  # 将接收到的数据添加到缓冲区

            frame = None  # 初始化frame变量
            while True:  # 循环提取帧数据
                extracted_frame = self._extract_frame()  # 直接调用私有方法提取一帧数据
                if extracted_frame is None:  # 如果没有提取到帧，跳出循环
                    break
                frame = extracted_frame  # 只保留最后一帧
                self.fps_tracker.append(time.time())  # 记录当前时间用于FPS计算

            if frame is not None:  # 如果成功提取到帧
                # 将每行反转后，直接展平成一个列表
                flat_data = []  # 创建空列表存储展平数据
                for row in frame:  # 遍历每一行
                    flat_data.extend(row[::-1].tolist())  # 反转行并直接扩展到大列表
                self.latest_reversed_data = flat_data[:config_utils.TOTAL_CELLS]  # 确保不超过24个元素

            return frame  # 返回提取到的帧
        except Exception as e:  # 捕获异常
            print(f"Receive error: {e}")  # 打印错误信息
            return None

    def _extract_frame(self):
        """从缓冲区中提取一帧数据"""
        start = self.buffer.find(b'\xAA')  # 查找帧头标识0xAA
        if start == -1:  # 如果没有找到帧头，返回None
            return None

        if len(self.buffer) < start + 3:  # 如果缓冲区数据不够，返回None
            return None

        # 解析数据长度，使用小端格式
        data_len = struct.unpack('<H', self.buffer[start + 1:start + 3])[0]
        total_len = 3 + data_len + 1  # 计算总长度(帧头3字节+数据+帧尾1字节)

        if len(self.buffer) < start + total_len:  # 如果缓冲区数据不够，返回None
            return None

        if self.buffer[start + total_len - 1] != 0x55:  # 检查帧尾是否正确
            print("Frame tail error!")  # 打印帧尾错误信息
            del self.buffer[:start + total_len]  # 删除错误数据
            return None

        # 提取有效数据
        data = self.buffer[start + 3:start + 3 + data_len]
        del self.buffer[:start + total_len]  # 从缓冲区删除已处理数据

        # 将数据转换为numpy数组并重塑为指定形状
        return np.frombuffer(data, dtype=np.float32).reshape((config_utils.ROWS, config_utils.COLS))

    def get_fps(self):
        """计算并返回FPS(每秒帧数)"""
        if len(self.fps_tracker) < 2:  # 如果跟踪器中数据不足，返回0
            return 0
        # 计算FPS：(帧数-1) / (最后时间-最初时间)
        return (len(self.fps_tracker) - 1) / (self.fps_tracker[-1] - self.fps_tracker[0])


class DataCell(QFrame):
    """数据单元格类，用于显示单个数据值"""

    def __init__(self, index, parent=None):
        """初始化数据单元格"""
        super().__init__(parent)  # 调用父类初始化
        self.index = index  # 存储单元格索引
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)  # 设置边框样式
        self.setLineWidth(1)  # 设置边框线宽

        # 创建主垂直布局
        layout = QVBoxLayout()
        layout.setSpacing(2)  # 设置控件间距
        layout.setContentsMargins(5, 5, 5, 5)  # 设置边距
        self.setLayout(layout)

        # 创建数据标签用于显示数值
        self.data_label = QLabel("0")
        self.data_label.setAlignment(Qt.AlignCenter)  # 设置文本居中
        self.data_label.setStyleSheet("""
            QLabel {
                font-weight: bold;      # 设置粗体
                font-size: 14px;        # 设置字体大小
            }
        """)
        layout.addWidget(self.data_label)  # 将标签添加到布局

        # 创建序号标签显示单元格编号
        self.index_label = QLabel(f"{index + 1}")
        self.index_label.setAlignment(Qt.AlignCenter)  # 设置文本居中
        self.index_label.setStyleSheet("""
            QLabel {
                font-size: 12px;        # 设置字体大小
                font-weight: bold;      # 设置粗体
                color: #000;            # 设置文字颜色
            }
        """)
        layout.addWidget(self.index_label)  # 将标签添加到布局

        # 设置初始值
        self.setValue(0)

    def setValue(self, value):
        """设置单元格的值并更新显示"""
        # 确保值在0-3300的范围内
        value = max(0, min(3300, value))

        # 计算颜色 (从绿色到红色的渐变)
        ratio = value / 3300  # 计算比例值
        red = int(255 * ratio)  # 根据比例计算红色分量
        green = int(255 * (1 - ratio))  # 根据比例计算绿色分量
        blue = 0  # 蓝色分量设为0
        color = QColor(red, green, blue)  # 创建颜色对象

        # 设置背景色
        palette = self.palette()  # 获取当前调色板
        palette.setColor(QPalette.Background, color)  # 设置背景色
        self.setAutoFillBackground(True)  # 启用自动填充背景
        self.setPalette(palette)  # 应用调色板

        # 设置文本颜色 (根据背景亮度自动选择黑色或白色)
        # 计算背景亮度，使用加权平均算法
        text_color = Qt.black if (red * 0.299 + green * 0.587 + blue * 0.114) > 150 else Qt.white
        palette.setColor(QPalette.WindowText, text_color)  # 设置文字颜色
        self.data_label.setPalette(palette)  # 应用到数据标签

        # 显示数值，转换为整数显示
        self.data_label.setText(f"{int(value)}")


class DataDisplay(QMainWindow):
    """主显示窗口类"""

    def __init__(self, receiver, conn):
        """初始化显示窗口"""
        super().__init__()  # 调用父类初始化

        self.status_label = None
        self.btn5 = None
        self.btn4 = None
        self.btn3 = None
        self.btn2 = None
        self.btn1 = None
        self.cells3 = None
        self.cells2 = None
        self.cells = None
        self.fps_label = None
        self.receiver = receiver  # 保存接收器对象
        self.conn = conn  # 保存连接对象
        self.data_storage = []  # 数据存储列表
        self.is_recording = False  # 录制状态标志

        self.my_stretch_ratios = []  # 向外传递的数据
        self.resistances_list = []

        # 添加预测窗口相关变量
        self.app_instance = None
        self.predict_window = None

        # 创建可拉伸外骨骼实例
        self.exoskeleton = perception_data_processor.StretchableExoskeleton()
        self.initUI()  # 初始化用户界面
        # 尝试加载已存在的校准文件
        self.load_existing_calibration_files()

        # 设置定时器刷新数据
        self.timer = QTimer(self)  # 创建定时器
        self.timer.timeout.connect(self.update_data)  # 连接超时信号到更新函数
        self.timer.start(20)  # 启动定时器，10毫秒间隔

    def load_existing_calibration_files(self):
        """尝试加载已存在的校准文件"""
        # 查找最新的初始值和预拉伸值文件
        initial_files = [f for f in os.listdir('.') if f.startswith('initial_values_') and f.endswith('.csv')]
        pre_stretch_files = [f for f in os.listdir('.') if f.startswith('pre_stretch_values_') and f.endswith('.csv')]

        # 如果找到文件，加载最新的
        latest_initial = None
        latest_pre_stretch = None

        if initial_files:
            latest_initial = sorted(initial_files)[-1]  # 按文件名排序，取最新的
            print(f"找到初始值文件: {latest_initial}")

        if pre_stretch_files:
            latest_pre_stretch = sorted(pre_stretch_files)[-1]  # 按文件名排序，取最新的
            print(f"找到预拉伸值文件: {latest_pre_stretch}")

        # 加载校准数据
        self.exoskeleton.load_calibration_data(latest_initial, latest_pre_stretch)

        if self.exoskeleton.is_calibrated():
            print("系统已完成校准")
            self.status_label.setText("系统状态: 已调用之前的校准文件 - 可进行拉伸量计算")
            self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #008800;")
            initial_info = self.exoskeleton.get_initial_stretch_info()
            if initial_info:
                avg_initial_stretch = np.mean(initial_info)
                print(f"平均初始拉伸比例: {avg_initial_stretch:.4f}")
        else:
            print("系统未完成校准，请先记录初始值和预拉伸值")

    def initUI(self):
        """初始化用户界面"""
        self.setWindowTitle('可拉伸外骨骼监控系统 - 实时数据监控 (0-3300)')
        self.setGeometry(100, 100, 1600, 350)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # 定义行配置：(标签文本, 单元格列表属性名)
        row_configs = [
            ("原始数据ADC电压:", "cells"),
            ("当前可拉伸电阻阻值:", "cells2"),
            ("当前拉伸率(0-1024):", "cells3")
        ]

        # 创建数据行
        for label_text, cells_attr in row_configs:
            row_layout = QHBoxLayout()
            row_layout.setSpacing(5)
            row_layout.setContentsMargins(10, 5, 10, 5)

            # 添加标签 - 增大字体并支持自动换行
            label = QLabel(label_text)
            label.setStyleSheet("""
                font-size: 18px; 
                font-weight: bold; 
                color: #333; 
                min-width: 150px;
                max-width: 150px;
                word-wrap: break-word;
                qproperty-alignment: AlignLeft AlignVCenter;
            """)
            label.setWordWrap(True)  # 启用自动换行
            label.setAlignment(Qt.AlignLeft | Qt.AlignTop)  # 顶部对齐
            row_layout.addWidget(label)

            # 创建单元格容器
            cells_container = QHBoxLayout()
            cells_container.setSpacing(2)
            cells_container.setContentsMargins(0, 0, 0, 0)

            # 创建单元格
            cells = []
            for i in range(config_utils.TOTAL_CELLS):
                cell = DataCell(i)
                cells_container.addWidget(cell)
                cells.append(cell)

            # 将单元格容器添加到行布局
            row_layout.addLayout(cells_container)

            # 设置单元格列表属性
            setattr(self, cells_attr, cells)
            main_layout.addLayout(row_layout)

        # 创建按钮水平布局
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.setContentsMargins(10, 5, 10, 5)

        # 创建按钮
        buttons = [
            ("记录初始值", self.button1_callback),
            ("记录预拉伸值", self.button2_callback),
            ("重新加载校准文件", self.button3_callback),
            ("记录当前手势电阻值", self.button4_callback),
            ("记录当前手势拉伸率", self.button5_callback)
        ]

        for text, callback in buttons:
            btn = QPushButton(text)
            btn.clicked.connect(callback)
            button_layout.addWidget(btn)
            setattr(self, f"btn{buttons.index((text, callback)) + 1}", btn)

        main_layout.addLayout(button_layout)

        # 添加状态显示标签
        self.status_label = QLabel("系统状态: 未校准")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #666;")
        self.update_status()
        main_layout.addWidget(self.status_label)

        # 添加FPS显示标签
        self.fps_label = QLabel("FPS: 0.0")
        self.fps_label.setAlignment(Qt.AlignCenter)
        self.fps_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")
        main_layout.addWidget(self.fps_label)

    def save_calibration_data(self, data, file_prefix):
        """辅助函数：保存校准数据到CSV文件"""
        try:
            # 生成文件名（带时间戳）
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"{file_prefix}_{timestamp}.csv"
            # 创建CSV文件并写入数据
            with open(filename, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                # 写入表头
                headers = [f"Sensor_{i + 1}" for i in range(config_utils.TOTAL_CELLS)]
                writer.writerow(headers)
                # 写入数据
                writer.writerow([f"{val:.2f}" for val in data])
            print(f"{file_prefix}已保存到文件: {filename}")
            print(f"保存的数据: {data}")
            return filename, timestamp
        except Exception as e:
            print(f"保存{file_prefix}时出错: {e}")
            return None, None

    def save_calibration_data_with_label(self, data, file_prefix, label_value):
        """增强版辅助函数：保存校准数据到CSV文件，添加label表头和对应的值，并保存到label/label_value对应的文件夹下"""
        try:
            # 使用"label/label_value"作为文件夹路径
            base_folder = "label"
            subfolder_name = str(label_value)
            folder_path = os.path.join(base_folder, subfolder_name)

            # 检查文件夹是否存在，如果不存在则创建（包括父文件夹）
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)
                print(f"创建文件夹路径: {folder_path}")

            # 生成文件名（带时间戳）
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"{file_prefix}_{timestamp}.csv"

            # 构建完整的文件路径
            full_path = os.path.join(folder_path, filename)

            # 创建CSV文件并写入数据
            with open(full_path, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)

                # 写入表头 - 添加label列在最前面
                headers = ["label"] + [f"Sensor_{i + 1}" for i in range(config_utils.TOTAL_CELLS)]
                writer.writerow(headers)

                # 写入数据 - label_value作为第一列，后面跟着传感器数据
                formatted_data = [str(label_value)] + [f"{val}" for val in data]
                writer.writerow(formatted_data)

            print(f"{file_prefix}已保存到文件: {full_path}")
            print(f"保存的数据: {formatted_data}")
            return full_path, timestamp

        except Exception as e:
            print(f"保存{file_prefix}时出错: {e}")
            return None, None

    def button1_callback(self):
        """按钮1回调函数：记录未拉伸状态的初始值到CSV文件"""
        print("点击按钮：记录未拉伸状态的初始值")
        try:
            # 获取当前的24个传感器数据
            current_data = self.receiver.latest_reversed_data.copy()
            # 保存数据
            filename, timestamp = self.save_calibration_data(current_data, "initial_values")
            if filename:
                # 更新按钮状态和文本
                self.btn1.setText(f"已保存初始值 ({timestamp})")
                self.btn1.setEnabled(False)
                # 更新外骨骼类的初始值
                self.exoskeleton.load_calibration_data(filename, None)
                # 更新状态显示
                self.update_status()
        except Exception as e:
            print(f"保存初始值时出错: {e}")

    def button2_callback(self):
        """按钮2回调函数：记录预拉伸值到CSV文件"""
        print("点击按钮：记录预拉伸值")
        try:
            # 获取当前的24个传感器数据
            current_data = self.receiver.latest_reversed_data.copy()
            # 保存数据
            filename, timestamp = self.save_calibration_data(current_data, "pre_stretch_values")
            if filename:
                # 更新按钮状态和文本
                self.btn2.setText(f"已保存预拉伸值 ({timestamp})")
                self.btn2.setEnabled(False)
                # 更新外骨骼类的预拉伸值
                self.exoskeleton.load_calibration_data(None, filename)
                # 更新状态显示
                self.update_status()
        except Exception as e:
            print(f"保存预拉伸值时出错: {e}")

    def button3_callback(self):
        """按钮3回调函数：重新加载校准文件"""
        print("点击按钮：重新加载校准文件")
        self.load_existing_calibration_files()
        self.update_status()

        # 重新启用按钮
        self.btn1.setEnabled(True)
        self.btn2.setEnabled(True)
        self.btn1.setText("记录初始值")
        self.btn2.setText("记录预拉伸值")

    def button4_callback(self):
        """按钮4回调函数：重新加载校准文件"""
        print("点击按钮：记录当前手势电阻值")
        self.update_status()
        # print(f"当前手势的电阻值分别为：{self.resistances_list}")
        self.save_calibration_data_with_label(self.resistances_list, "resistances_list",'1')


    def button5_callback(self):
        """按钮5回调函数：重新加载校准文件"""
        print("点击按钮：记录当前手势拉伸率")
        self.update_status()
        # print(f"当前手势的拉伸比例分别为：{self.my_stretch_ratios}")
        self.save_calibration_data_with_label(self.my_stretch_ratios, "my_stretch_ratios",'1')


    def update_status(self):
        """更新状态显示"""
        if self.exoskeleton.is_calibrated():
            self.status_label.setText("系统状态: 已重新校准 - 可进行拉伸量计算")
            self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #008800;")
        else:
            self.status_label.setText("系统状态: 未校准 - 请记录初始值和预拉伸值")
            self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #cc0000;")

    def update_data(self):
        """更新数据显示"""
        try:
            # 接收数据
            frame = self.receiver.receive(self.conn)  # 从连接接收数据
            if frame is not None:  # 如果接收到有效数据
                # 更新FPS显示
                fps = self.receiver.get_fps()  # 获取当前FPS
                self.fps_label.setText(f"FPS: {fps:.1f}")  # 更新FPS标签

                # 更新所有单元格
                for i, value in enumerate(self.receiver.latest_reversed_data):  # 遍历最新数据
                    if i < len(self.cells):  # 确保索引有效
                        self.cells[i].setValue(value)  # 更新单元格值
                # 如果已完成校准，计算实时拉伸量
                if self.exoskeleton.is_calibrated():
                    current_voltages = self.receiver.latest_reversed_data
                    resistances, stretch_ratios = self.exoskeleton.calculate_real_time_stretch(current_voltages)
                    self.my_stretch_ratios = stretch_ratios
                    self.resistances_list = resistances
                    # print(stretch_ratios)
                    # 更新所有单元格
                    for i, value in enumerate(resistances):  # 遍历最新数据
                        if i < len(self.cells2):  # 确保索引有效
                            self.cells2[i].setValue(value)  # 更新单元格值
                    for i, value in enumerate(stretch_ratios):  # 遍历最新数据
                        if i < len(self.cells3):  # 确保索引有效
                            self.cells3[i].setValue(value)  # 更新单元格值
                    if stretch_ratios:
                        # 这里可以添加实时拉伸量的显示逻辑
                        # 例如更新状态栏显示平均拉伸量
                        avg_stretch = np.mean(stretch_ratios)
                        # 可以在这里添加更多的实时数据显示逻辑
                        pass
                        
                    # 调用预测接口显示预测结果
                    if len(resistances) == 24:
                        if self.predict_window is None:
                            self.app_instance, self.predict_window = predict_and_show(resistances)
                        else:
                            # 更新预测窗口中的数据
                            self.predict_window.updatePrediction(resistances)
                        # 处理Qt事件循环
                        if self.app_instance.hasPendingEvents():
                            self.app_instance.processEvents()
        except Exception as e:  # 捕获异常
            print(f"Update error: {e}")  # 打印错误信息

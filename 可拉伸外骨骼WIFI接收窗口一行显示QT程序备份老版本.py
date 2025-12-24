# 导入所需的库
import socket  # 用于网络通信
import struct  # 用于解析二进制数据
import numpy as np  # 用于数组处理
import time  # 用于时间相关功能
from collections import deque  # 用于高效队列操作
# 导入PyQt5相关组件用于GUI界面
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
                             QLabel, QVBoxLayout, QFrame, QPushButton)

from PyQt5.QtCore import Qt, QTimer  # Qt核心功能和定时器
from PyQt5.QtGui import QColor, QPalette  # Qt图形界面相关
import csv,os,sys

# 定义数组的行数和列数
ROWS = 6  # 数组行数
COLS = 4  # 数组列数
TOTAL_CELLS = ROWS * COLS  # 计算总单元格数，总共24个元素

# 电阻计算相关常量
REFERENCE_VOLTAGE = 3300.0  # 参考电压 (mV)
REFERENCE_RESISTANCE = 10000.0  # 参考电阻 (欧姆)

class StretchableExoskeleton:
    """可拉伸外骨骼类，用于计算电阻值和拉伸量"""

    def __init__(self):
        """初始化可拉伸外骨骼类"""
        self.initial_voltages = None  # 未拉伸状态的初始电压值
        self.pre_stretch_voltages = None  # 预拉伸状态的电压值
        self.initial_resistances = None  # 初始电阻值
        self.pre_stretch_resistances = None  # 预拉伸电阻值
        self.initial_stretch_ratios = None  # 初始拉伸比例（由于骨骼长度不同）

        # 传感器配置参数
        self.voltage_ref = REFERENCE_VOLTAGE
        self.r_ref = REFERENCE_RESISTANCE

    def voltage_to_resistance(self, voltage):
        """
        根据分压原理计算电阻值
        使用公式: R = R_ref * (V_ref - V) / V
        其中 R_ref 是参考电阻，V_ref 是参考电压，V 是测量电压
        """
        if voltage <= 0 or voltage >= self.voltage_ref:
            return 0  # 避免除零错误和无效值
        resistance = self.r_ref * (self.voltage_ref - voltage) / voltage
        return resistance

    def load_calibration_data(self, initial_file=None, pre_stretch_file=None):
        """
        读取校准数据CSV文件
        """
        try:
            # 读取初始值文件
            if initial_file and os.path.exists(initial_file):
                with open(initial_file, 'r') as csvfile:
                    reader = csv.reader(csvfile)
                    headers = next(reader)  # 跳过表头
                    data_row = next(reader)  # 读取数据行
                    self.initial_voltages = [float(val) for val in data_row]
                    # 计算初始电阻值
                    self.initial_resistances = [self.voltage_to_resistance(v)
                                                for v in self.initial_voltages]
                    print(f"成功加载初始值文件: {initial_file}")
            else:
                print("未找到初始值文件")

            # 读取预拉伸值文件
            if pre_stretch_file and os.path.exists(pre_stretch_file):
                with open(pre_stretch_file, 'r') as csvfile:
                    reader = csv.reader(csvfile)
                    headers = next(reader)  # 跳过表头
                    data_row = next(reader)  # 读取数据行
                    self.pre_stretch_voltages = [float(val) for val in data_row]
                    # 计算预拉伸电阻值
                    self.pre_stretch_resistances = [self.voltage_to_resistance(v)
                                                    for v in self.pre_stretch_voltages]
                    print(f"成功加载预拉伸值文件: {pre_stretch_file}")
            else:
                print("未找到预拉伸值文件")

            # 计算初始拉伸比例（由于骨骼长度不同）
            if self.initial_resistances and self.pre_stretch_resistances:
                self.initial_stretch_ratios = []
                for i in range(len(self.initial_resistances)):
                    if self.initial_resistances[i] > 0:
                        ratio = (self.pre_stretch_resistances[i] - self.initial_resistances[i]) / self.initial_resistances[i]
                        self.initial_stretch_ratios.append(ratio)
                    else:
                        self.initial_stretch_ratios.append(0)
                print("成功计算初始拉伸比例")

        except Exception as e:
            print(f"加载校准数据时出错: {e}")

    def calculate_real_time_stretch(self, current_voltages):
        """
        计算实时拉伸量
        返回: (当前电阻值列表, 实时拉伸比例列表)
        """
        if not self.pre_stretch_resistances:
            return None, None

        # 计算当前电阻值
        current_resistances = [self.voltage_to_resistance(v) for v in current_voltages]

        # 计算实时拉伸比例：(当前电阻-预拉伸电阻)/预拉伸电阻
        real_time_stretch_ratios = []
        for i in range(len(current_resistances)):
            if self.pre_stretch_resistances[i] > 0:
                ratio = (current_resistances[i] - self.pre_stretch_resistances[i]) / self.pre_stretch_resistances[i]
                real_time_stretch_ratios.append(ratio)
            else:
                real_time_stretch_ratios.append(0)

        return current_resistances, real_time_stretch_ratios

    def get_initial_stretch_info(self):
        """获取初始拉伸信息"""
        return self.initial_stretch_ratios

    def is_calibrated(self):
        """检查是否已完成校准"""
        return self.initial_resistances is not None and self.pre_stretch_resistances is not None

class HighSpeedReceiver:
    """高速数据接收器类，负责从网络接收和解析数据"""

    def __init__(self):
        """初始化接收器"""
        self.buffer = bytearray()  # 创建字节缓冲区用于存储接收到的数据
        self.latest_reversed_data = [0] * TOTAL_CELLS  # 初始化24个0作为最新数据

        # --- FPS 统计相关的变量 (MODIFIED) ---
        self.frame_count = 0             # 在一个时间周期内接收到的帧数
        self.last_fps_calc_time = time.time() # 上次计算FPS的时间
        self.stable_fps = 0.0            # 存储稳定计算出的FPS值
        # --- End of MODIFIED section ---

    def receive(self, sock):
        """从socket接收数据并解析"""
        try:
            data = sock.recv(4096)  # 从socket接收最多4096字节数据
            if not data:  # 如果没有接收到数据，返回None
                return None
            self.buffer.extend(data)  # 将接收到的数据添加到缓冲区

            frame = None  # 初始化frame变量
            frame_received_in_this_call = False # 标记本次调用是否收到新帧
            while True:  # 循环提取帧数据
                extracted_frame = self._extract_frame()  # 直接调用私有方法提取一帧数据
                if extracted_frame is None:  # 如果没有提取到帧，跳出循环
                    break
                frame = extracted_frame  # 只保留最后一帧

                # --- 每成功提取一帧，计数器加一 (MODIFIED) ---
                self.frame_count += 1
                frame_received_in_this_call = True
                # --- End of MODIFIED section ---

            if frame is not None:  # 如果成功提取到帧
                # 将每行反转后，直接展平成一个列表
                flat_data = []  # 创建空列表存储展平数据
                for row in frame:  # 遍历每一行
                    flat_data.extend(row[::-1].tolist())  # 反转行并直接扩展到大列表
                self.latest_reversed_data = flat_data[:TOTAL_CELLS]  # 确保不超过24个元素

            # 仅在实际收到帧时返回frame，否则返回None，避免不必要的UI更新
            return frame if frame_received_in_this_call else None

        except Exception as e:  # 捕获异常
            print(f"Receive error: {e}")  # 打印错误信息
            return None  # 返回None

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
        return np.frombuffer(data, dtype=np.float32).reshape((ROWS, COLS))

    def get_fps(self):
        """
        计算并返回稳定的FPS(每秒帧数)
        (MODIFIED - New Logic)
        """
        current_time = time.time()
        time_elapsed = current_time - self.last_fps_calc_time

        # 每隔1秒计算一次FPS
        if time_elapsed >= 1.0:
            # 计算FPS
            self.stable_fps = self.frame_count / time_elapsed
            # 重置计数器和计时器
            self.frame_count = 0
            self.last_fps_calc_time = current_time

        # 在计算间隔内，始终返回上一次计算出的稳定值
        return self.stable_fps


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
        self.fps_label = None
        self.btn3 = None
        self.btn2 = None
        self.cells = None
        self.hbox = None
        self.btn1 = None
        self.receiver = receiver  # 保存接收器对象
        self.conn = conn  # 保存连接对象
        self.data_storage = []  # 数据存储列表
        self.is_recording = False  # 录制状态标志
        self.initUI()  # 初始化用户界面
        # 设置定时器刷新数据
        self.timer = QTimer(self)  # 创建定时器
        self.timer.timeout.connect(self.update_data)  # 连接超时信号到更新函数
        self.timer.start(10)  # 启动定时器，10毫秒间隔

    def initUI(self):
        """初始化用户界面"""
        self.setWindowTitle('实时数据监控 (0-3300) - 水平排列')  # 设置窗口标题
        self.setGeometry(100, 100, 1600, 200)  # 设置窗口位置和大小
        central_widget = QWidget()  # 创建中央部件
        self.setCentralWidget(central_widget)  # 设置为中央部件
        main_layout = QVBoxLayout()  # 创建主垂直布局
        central_widget.setLayout(main_layout)  # 应用布局
        # 创建水平布局用于排列数据单元格
        self.hbox = QHBoxLayout()
        self.hbox.setSpacing(5)  # 设置间距
        self.hbox.setContentsMargins(10, 5, 10, 5)  # 设置边距
        self.cells = []  # 创建单元格列表
        # 创建24个水平排列的单元格
        for i in range(TOTAL_CELLS):
            cell = DataCell(i)  # 创建数据单元格
            self.hbox.addWidget(cell)  # 添加到水平布局
            self.cells.append(cell)  # 添加到单元格列表
        main_layout.addLayout(self.hbox)  # 将水平布局添加到主布局
        # 创建按钮水平布局
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.setContentsMargins(10, 5, 10, 5)
        # 创建按钮1：开始录制
        self.btn1 = QPushButton("记录初始值")
        self.btn1.clicked.connect(self.button1_callback)
        button_layout.addWidget(self.btn1)
        # 创建按钮2：停止录制
        self.btn2 = QPushButton("记录预拉伸值")
        self.btn2.clicked.connect(self.button2_callback)
        button_layout.addWidget(self.btn2)
        # 创建按钮3：保存数据
        self.btn3 = QPushButton("待定使用")
        self.btn3.clicked.connect(self.button3_callback)
        button_layout.addWidget(self.btn3)
        main_layout.addLayout(button_layout)  # 添加按钮布局到主布局
        # 添加FPS显示标签
        self.fps_label = QLabel("FPS: 0.0")
        self.fps_label.setAlignment(Qt.AlignCenter)  # 设置文本居中
        self.fps_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")  # 设置样式
        main_layout.addWidget(self.fps_label)  # 添加到布局

    def button1_callback(self):
        """按钮1回调函数：记录未拉伸状态的初始值到CSV文件"""
        print("点击按钮：记录未拉伸状态的初始值")

        try:
            # 获取当前的24个传感器数据
            current_data = self.receiver.latest_reversed_data.copy()

            # 生成文件名（带时间戳）
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"initial_values_{timestamp}.csv"

            # 创建CSV文件并写入数据
            with open(filename, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)

                # 写入表头
                headers = [f"Sensor_{i+1}" for i in range(TOTAL_CELLS)]
                writer.writerow(headers)

                # 写入数据
                writer.writerow([f"{val:.2f}" for val in current_data])

            print(f"初始值已保存到文件: {filename}")
            print(f"保存的数据: {current_data}")

            # 更新按钮状态和文本
            self.btn1.setText(f"已保存初始值 ({timestamp})")
            self.btn1.setEnabled(False)

        except Exception as e:
            print(f"保存初始值时出错: {e}")

    def button2_callback(self):
        """按钮2回调函数：记录预拉伸值到CSV文件"""
        print("点击按钮：记录预拉伸值")

        try:
            # 获取当前的24个传感器数据
            current_data = self.receiver.latest_reversed_data.copy()

            # 生成文件名（带时间戳）
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"pre_stretch_values_{timestamp}.csv"

            # 创建CSV文件并写入数据
            with open(filename, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)

                # 写入表头
                headers = [f"Sensor_{i+1}" for i in range(TOTAL_CELLS)]
                writer.writerow(headers)

                # 写入数据
                writer.writerow([f"{val:.2f}" for val in current_data])

            print(f"预拉伸值已保存到文件: {filename}")
            print(f"保存的数据: {current_data}")

            # 更新按钮状态和文本
            self.btn2.setText(f"已保存预拉伸值 ({timestamp})")
            self.btn2.setEnabled(False)

        except Exception as e:
            print(f"保存预拉伸值时出错: {e}")


    def button3_callback(self):
        """按钮3回调函数：保存数据"""
        print("按钮3被点击：保存数据")
        print(f"当前存储的数据量: {len(self.data_storage)}")
        # 这里可以添加您的数据保存逻辑
        self.btn1.setEnabled(True)
        self.btn2.setEnabled(True)

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

                # 如果正在录制，保存数据
                if self.is_recording:
                    self.data_storage.append(self.receiver.latest_reversed_data.copy())
        except Exception as e:  # 捕获异常
            print(f"Update error: {e}")  # 打印错误信息


# 程序入口点
if __name__ == "__main__":
    HOST, PORT = '0.0.0.0', 8888  # 定义服务器地址和端口
    receiver = HighSpeedReceiver()  # 创建接收器实例

    # 创建socket连接
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # 创建TCP socket
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # 禁用Nagle算法提高实时性
    s.bind((HOST, PORT))  # 绑定地址和端口
    s.listen()  # 开始监听连接
    print(f"Listening on {HOST}:{PORT}...")  # 打印监听信息
    conn, addr = s.accept()  # 接受客户端连接
    print(f"Connected by {addr}")  # 打印连接信息

    # 启动Qt应用
    app = QApplication([])  # 创建Qt应用程序
    display = DataDisplay(receiver, conn)  # 创建显示窗口，传入conn对象
    display.show()  # 显示窗口

    try:
        app.exec_()  # 运行应用程序事件循环
    except KeyboardInterrupt:  # 捕获键盘中断
        print("\nStopped.")  # 打印停止信息
    finally:
        conn.close()  # 关闭客户端连接
        s.close()  # 关闭服务器socket

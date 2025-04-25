import serial
import struct
import traceback
import glove_data_pb2
import time
import numpy as np
from PyQt5 import QtWidgets
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        # 主窗口设置
        self.setWindowTitle('Real-time Z Channel (12×6)')
        self.resize(800, 400)

        # 创建图形部件
        self.graphWidget = pg.PlotWidget()
        self.setCentralWidget(self.graphWidget)

        # 图像显示设置
        self.img = pg.ImageItem()
        self.graphWidget.addItem(self.img)
        self.graphWidget.setAspectLocked(False)
        self.graphWidget.setLabel('left', 'Y Position')
        self.graphWidget.setLabel('bottom', 'X Position')

        # 颜色条
        self.hist = pg.HistogramLUTItem()
        self.hist.setImageItem(self.img)
        self.hist.gradient.loadPreset('viridis')
        self.graphWidget.addItem(self.hist)

        # 初始化数据
        self.z_data = np.zeros((6, 12))
        self.img.setImage(self.z_data)
        self.img.setLevels([0, 255])  # 固定范围

        # 帧率计数器
        self.frame_count = 0
        self.last_time = time.time()

        # 串口设置
        self.serial_port = None
        self.init_serial()

        # 定时器更新
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_data)
        self.timer.start(0)  # 尽可能快的更新

    def init_serial(self):
        try:
            self.serial_port = serial.Serial('COM9', 6000000, timeout=0.1)
            print("串口连接成功")
        except Exception as e:
            print(f"串口连接失败: {str(e)}")
            self.serial_port = None

    def receive_protobuf_data(self):
        if not self.serial_port or not self.serial_port.is_open:
            return None

        # 等待帧开始标记
        while self.serial_port.in_waiting > 0:
            start_byte = self.serial_port.read(1)
            if start_byte == b'\xAA':
                break

        if not self.serial_port.in_waiting >= 3:  # 至少需要长度+结束标记
            return None

        # 读取消息长度
        length_bytes = self.serial_port.read(2)
        message_length = struct.unpack('<H', length_bytes)[0]

        # 检查数据是否足够
        if self.serial_port.in_waiting < message_length + 1:
            return None

        # 读取消息内容
        message_data = self.serial_port.read(message_length)
        end_byte = self.serial_port.read(1)

        if end_byte != b'\x55':
            print("帧结束标记错误!")
            return None

        try:
            all_sensors_data = glove_data_pb2.AllSensorsData()
            all_sensors_data.ParseFromString(message_data)
            return all_sensors_data
        except Exception as e:
            print(f"Protobuf解析错误: {str(e)}")
            return None

    def update_data(self):
        all_sensors_data = self.receive_protobuf_data()
        if all_sensors_data is None:
            return

        # 帧率计算
        self.frame_count += 1
        current_time = time.time()
        if current_time - self.last_time >= 1.0:
            fps = self.frame_count / (current_time - self.last_time)
            self.setWindowTitle(f'Real-time Z Channel (12×6) - FPS: {fps:.1f}')
            self.frame_count = 0
            self.last_time = current_time

        # 数据处理
        sensor = all_sensors_data.sensors[0]
        points_data = np.empty((72, 3), dtype=np.float32)

        for i, point in enumerate(sensor.points[1:]):  # 跳过第0点
            points_data[i, 0] = point.x
            points_data[i, 1] = point.y
            points_data[i, 2] = point.z

        z_data = points_data.reshape(6, 12, 3)[:, :, 2]
        self.img.setImage(z_data.T)  # 注意转置使方向正确

        # 自动调整范围
        min_val = np.min(z_data)
        max_val = np.max(z_data)
        self.img.setLevels([min_val, max_val])

if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    main = MainWindow()
    main.show()

    # 确保程序退出时关闭串口
    def on_exit():
        if main.serial_port and main.serial_port.is_open:
            main.serial_port.close()
        app.quit()

    app.aboutToQuit.connect(on_exit)
    sys.exit(app.exec_())

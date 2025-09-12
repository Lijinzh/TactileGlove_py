# sensor_visualizer.py

import sys
import serial
import struct
import time
from collections import deque
from dataclasses import dataclass
from threading import Thread, Lock

import pyqtgraph as pg
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout, QLabel
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont

# --- 配置区 (Configuration Area) ---
SERIAL_PORT = 'COM10'
BAUD_RATE = 6000000
PLOT_HISTORY_LEN = 200

# --- 数据包结构定义 (Data Packet Structure Definition) ---
PACKET_FORMAT = '<BB10fB'
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)
PACKET_HEADER = (0xAA, 0xBB)

@dataclass
class SensorData:
    accel_x: float = 0.0
    accel_y: float = 0.0
    accel_z: float = 0.0
    gyro_x: float = 0.0
    gyro_y: float = 0.0
    gyro_z: float = 0.0
    mag_x: float = 0.0
    mag_y: float = 0.0
    mag_z: float = 0.0
    pressure: float = 0.0

class SerialDataReader:
    """
    重构后的串口读取器，在一个独立的后台线程中运行。
    (Refactored SerialDataReader to run in a separate background thread.)
    """
    def __init__(self, port, baudrate):
        try:
            self.ser = serial.Serial(port, baudrate, timeout=0.1)
            print(f"成功打开串口 {port}")
        except serial.SerialException as e:
            print(f"错误：无法打开串口 {port}。请检查端口号是否正确，或设备是否被占用。")
            print(e)
            sys.exit(1)

        self.buffer = bytearray()
        self.latest_data = None
        self.lock = Lock()
        self.running = False
        self.thread = None

    def _calculate_checksum(self, data_bytes: bytes) -> int:
        checksum = 0
        for byte in data_bytes:
            checksum ^= byte
        return checksum

    def _read_loop(self):
        """这个函数会在后台线程中持续运行 (This function runs continuously in the background thread)"""
        while self.running:
            # 1. 从串口读取数据
            self.buffer.extend(self.ser.read(self.ser.in_waiting or 1))

            # 2. 在缓冲区中寻找并解析数据包
            while len(self.buffer) >= PACKET_SIZE:
                header_index = self.buffer.find(bytes(PACKET_HEADER))
                if header_index == -1:
                    self.buffer = self.buffer[-(PACKET_SIZE - 1):]
                    break

                if header_index > 0:
                    self.buffer = self.buffer[header_index:]

                if len(self.buffer) < PACKET_SIZE:
                    break

                packet_bytes = self.buffer[:PACKET_SIZE]
                self.buffer = self.buffer[PACKET_SIZE:]

                try:
                    header1, header2, *values, received_checksum = struct.unpack(PACKET_FORMAT, packet_bytes)
                    data_bytes_for_checksum = packet_bytes[2:-1]
                    calculated_checksum = self._calculate_checksum(data_bytes_for_checksum)

                    if calculated_checksum == received_checksum:
                        # 3. 如果数据有效，就加锁并更新 latest_data
                        with self.lock:
                            self.latest_data = SensorData(*values)
                    else:
                        print(f"校验和错误！接收到: {received_checksum}, 计算出: {calculated_checksum}")
                except struct.error:
                    print("数据包解包错误，可能已损坏。")

            time.sleep(0.001) # 短暂休眠，避免CPU占用过高

    def start(self):
        """启动后台读取线程"""
        if self.thread is None:
            self.running = True
            self.thread = Thread(target=self._read_loop, daemon=True)
            self.thread.start()
            print("后台串口读取线程已启动。")

    def get_latest_data(self) -> SensorData | None:
        """
        GUI线程调用此函数来安全地获取最新数据。
        (The GUI thread calls this function to safely get the latest data.)
        """
        with self.lock:
            data = self.latest_data
            self.latest_data = None # 获取后清空，避免重复绘图
            return data

    def close(self):
        """停止线程并关闭串口"""
        self.running = False
        if self.thread:
            self.thread.join()
        if self.ser and self.ser.is_open:
            self.ser.close()

class RealTimePlotter(QMainWindow):
    def __init__(self, data_reader: SerialDataReader):
        super().__init__()
        self.reader = data_reader
        self.setWindowTitle('MuscleAvatar 传感器数据实时监控')
        self.setGeometry(100, 100, 1200, 800)
        self.time_history = deque(maxlen=PLOT_HISTORY_LEN)
        self.accel_history = {'x': deque(maxlen=PLOT_HISTORY_LEN), 'y': deque(maxlen=PLOT_HISTORY_LEN), 'z': deque(maxlen=PLOT_HISTORY_LEN)}
        self.gyro_history = {'x': deque(maxlen=PLOT_HISTORY_LEN), 'y': deque(maxlen=PLOT_HISTORY_LEN), 'z': deque(maxlen=PLOT_HISTORY_LEN)}
        self.mag_history = {'x': deque(maxlen=PLOT_HISTORY_LEN), 'y': deque(maxlen=PLOT_HISTORY_LEN), 'z': deque(maxlen=PLOT_HISTORY_LEN)}

        self._setup_ui()

        # 启动后台数据读取
        self.reader.start()

        self.timer = QTimer()
        self.timer.setInterval(20) # 50Hz 刷新率
        self.timer.timeout.connect(self.update_plot)
        self.timer.start()

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        plot_widget = pg.GraphicsLayoutWidget()
        main_layout.addWidget(plot_widget)
        self.accel_plot = plot_widget.addPlot(row=0, col=0, title="加速度计 (m/s^2)")
        self.accel_plot.addLegend()
        self.accel_plot.showGrid(x=True, y=True)
        self.accel_curves = {
            'x': self.accel_plot.plot(pen='r', name='X'),
            'y': self.accel_plot.plot(pen='g', name='Y'),
            'z': self.accel_plot.plot(pen='b', name='Z')
        }
        self.gyro_plot = plot_widget.addPlot(row=1, col=0, title="陀螺仪 (rad/s)")
        self.gyro_plot.addLegend()
        self.gyro_plot.showGrid(x=True, y=True)
        self.gyro_curves = {
            'x': self.gyro_plot.plot(pen='r', name='X'),
            'y': self.gyro_plot.plot(pen='g', name='Y'),
            'z': self.gyro_plot.plot(pen='b', name='Z')
        }
        self.mag_plot = plot_widget.addPlot(row=2, col=0, title="磁力计 (uT)")
        self.mag_plot.addLegend()
        self.mag_plot.showGrid(x=True, y=True)
        self.mag_curves = {
            'x': self.mag_plot.plot(pen='r', name='X'),
            'y': self.mag_plot.plot(pen='g', name='Y'),
            'z': self.mag_plot.plot(pen='b', name='Z')
        }
        status_layout = QGridLayout()
        main_layout.addLayout(status_layout)
        status_layout.addWidget(QLabel("<b>气压 (hPa):</b>"), 0, 0)
        self.pressure_label = QLabel("N/A")
        font = self.pressure_label.font()
        font.setPointSize(16)
        self.pressure_label.setFont(font)
        status_layout.addWidget(self.pressure_label, 0, 1)

    def update_plot(self):
        """
        定时器调用的核心更新函数。
        这个函数现在非常轻量，只从后台线程获取最新的数据并更新图表。
        """
        sensor_data = self.reader.get_latest_data()

        # 只有在后台线程提供了新数据时才更新图表
        if sensor_data:
            # --- 更新数据缓冲区 ---
            self.time_history.append(time.time())
            self.accel_history['x'].append(sensor_data.accel_x)
            self.accel_history['y'].append(sensor_data.accel_y)
            self.accel_history['z'].append(sensor_data.accel_z)
            self.gyro_history['x'].append(sensor_data.gyro_x)
            self.gyro_history['y'].append(sensor_data.gyro_y)
            self.gyro_history['z'].append(sensor_data.gyro_z)
            self.mag_history['x'].append(sensor_data.mag_x)
            self.mag_history['y'].append(sensor_data.mag_y)
            self.mag_history['z'].append(sensor_data.mag_z)

            # --- 更新图表曲线 ---
            time_axis = list(self.time_history)
            for axis in ['x', 'y', 'z']:
                self.accel_curves[axis].setData(time_axis, list(self.accel_history[axis]))
                self.gyro_curves[axis].setData(time_axis, list(self.gyro_history[axis]))
                self.mag_curves[axis].setData(time_axis, list(self.mag_history[axis]))

            # --- 更新文本标签 ---
            self.pressure_label.setText(f"{sensor_data.pressure:.2f}")

    def closeEvent(self, event):
        self.reader.close()
        print("后台线程已停止，串口已关闭。程序退出。")
        event.accept()

if __name__ == '__main__':
    print("正在启动传感器数据可视化程序...")
    app = QApplication(sys.argv)
    reader = SerialDataReader(SERIAL_PORT, BAUD_RATE)
    plotter = RealTimePlotter(reader)
    plotter.show()
    sys.exit(app.exec())


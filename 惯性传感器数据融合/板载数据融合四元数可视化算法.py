# pose_visualizer.py
# Description:
# This script visualizes pre-computed, stable Euler angles sent from an ESP32.
# It is the client counterpart to the firmware that uses ReefwingAHRS on-board
# to generate reliable, decoupled roll, pitch, and yaw data.

import sys
import serial
import struct
import time
import numpy as np
from threading import Thread, Lock

import pyqtgraph as pg
import pyqtgraph.opengl as gl
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont

# --- 配置区 (Configuration Area) ---
SERIAL_PORT = 'COM10'
BAUD_RATE = 6000000

# --- [核心] 数据包结构定义 ---
# 对应ESP32发送的欧拉角数据包
# 2B (header) + 13*float (3 euler + 10 raw) + 1B (checksum) = 55 bytes
PACKET_FORMAT = '<BB13fB'
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)
PACKET_HEADER = (0xAA, 0xBB)

class SerialDataReader:
    """在独立的后台线程中运行的串口读取器，负责解析和校验数据包。"""
    def __init__(self, port, baudrate):
        try:
            self.ser = serial.Serial(port, baudrate, timeout=0.1)
            print(f"成功打开串口 {port}")
        except serial.SerialException as e:
            print(f"错误：无法打开串口 {port}。请检查端口号或设备是否被占用。")
            print(e); sys.exit(1)
        self.buffer = bytearray()
        self.latest_data_packet = None
        self.lock = Lock()
        self.running = False
        self.thread = None

    def _calculate_checksum(self, data_bytes: bytes) -> int:
        """在Python中重新实现ESP32的校验和算法"""
        checksum = 0
        for byte in data_bytes:
            checksum ^= byte
        return checksum

    def _read_loop(self):
        """线程主循环，持续读取、解析和校验数据。"""
        while self.running:
            self.buffer.extend(self.ser.read(self.ser.in_waiting or 1))
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
                    *_, received_checksum = struct.unpack(PACKET_FORMAT, packet_bytes)
                    data_bytes_for_checksum = packet_bytes[2:-1]
                    if self._calculate_checksum(data_bytes_for_checksum) == received_checksum:
                        with self.lock:
                            self.latest_data_packet = np.array(struct.unpack('<13f', data_bytes_for_checksum))
                except struct.error:
                    pass
            time.sleep(0.001)

    def start(self):
        if self.thread is None:
            self.running = True
            self.thread = Thread(target=self._read_loop, daemon=True)
            self.thread.start()
            print("后台串口读取线程已启动。")

    def get_latest_data(self) -> np.ndarray | None:
        """获取最新的有效数据包"""
        with self.lock:
            data = self.latest_data_packet
            self.latest_data_packet = None
            return data

    def close(self):
        self.running = False
        if self.thread: self.thread.join()
        if self.ser and self.ser.is_open: self.ser.close()

class PoseVisualizer3D(QMainWindow):
    """负责3D姿态可视化和数据显示的GUI"""
    def __init__(self, data_reader: SerialDataReader):
        super().__init__()
        self.reader = data_reader
        self.setWindowTitle('ESP32 板载融合姿态可视化 (欧拉角)')
        self.setGeometry(100, 100, 1200, 800)

        self.altitude = 0.0
        self.initial_pressure = None

        self._setup_ui()
        self.reader.start()

        self.timer = QTimer()
        self.timer.setInterval(20) # 50Hz (20ms) 刷新率
        self.timer.timeout.connect(self.update_ui)
        self.timer.start()

    def _setup_ui(self):
        """构建UI界面"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        self.view3d = gl.GLViewWidget()
        self.view3d.setCameraPosition(distance=5)
        main_layout.addWidget(self.view3d, stretch=2)
        grid = gl.GLGridItem(); grid.scale(2, 2, 1); self.view3d.addItem(grid)

        # [核心修改] 调换X轴和Y轴的缩放比例，改变长方体形状
        verts = np.array([ [0.5, 0.5, 0.5], [0.5, 0.5, -0.5], [0.5, -0.5, 0.5], [0.5, -0.5, -0.5], [-0.5, 0.5, 0.5], [-0.5, 0.5, -0.5], [-0.5, -0.5, 0.5], [-0.5, -0.5, -0.5] ]) * np.array([1.0, 2.0, 0.2])

        faces = np.array([ [0, 2, 3], [0, 3, 1], [4, 5, 7], [4, 7, 6], [0, 1, 5], [0, 5, 4], [2, 6, 7], [2, 7, 3], [1, 3, 7], [1, 7, 5], [0, 4, 6], [0, 6, 2] ])
        colors = np.array([ [1, 0, 0, 1], [1, 0.5, 0, 1], [1, 1, 0, 1], [0.5, 1, 0, 1], [0, 1, 0, 1], [0, 1, 0.5, 1], [0, 1, 1, 1], [0, 0.5, 1, 1] ])
        self.mesh = gl.GLMeshItem(vertexes=verts, faces=faces, vertexColors=colors, smooth=False, drawEdges=True)
        self.view3d.addItem(self.mesh)

        data_panel = QWidget(); data_layout = QVBoxLayout(data_panel); main_layout.addWidget(data_panel, stretch=1)
        title_font = QFont(); title_font.setPointSize(16); title_font.setBold(True)
        data_font = QFont(); data_font.setPointSize(12)

        pose_label = QLabel("姿态数据 (Pose)"); pose_label.setFont(title_font); data_layout.addWidget(pose_label)
        self.roll_label = QLabel("Roll:  0.0°"); self.roll_label.setFont(data_font); data_layout.addWidget(self.roll_label)
        self.pitch_label = QLabel("Pitch: 0.0°"); self.pitch_label.setFont(data_font); data_layout.addWidget(self.pitch_label)
        self.yaw_label = QLabel("Yaw:   0.0°"); self.yaw_label.setFont(data_font); data_layout.addWidget(self.yaw_label)

        raw_label = QLabel("原始数据监控 (Raw)"); raw_label.setFont(title_font); data_layout.addWidget(raw_label)
        self.accel_label = QLabel("Acc (m/s²): 0, 0, 0"); self.accel_label.setFont(data_font); data_layout.addWidget(self.accel_label)
        self.gyro_label = QLabel("Gyro (rad/s): 0, 0, 0"); self.gyro_label.setFont(data_font); data_layout.addWidget(self.gyro_label)
        self.mag_label = QLabel("Mag (uT):   0, 0, 0"); self.mag_label.setFont(data_font); data_layout.addWidget(self.mag_label)
        self.pressure_label = QLabel("Pressure: 0 hPa"); self.pressure_label.setFont(data_font); data_layout.addWidget(self.pressure_label)

        alt_label = QLabel("高度估算 (Altitude)"); alt_label.setFont(title_font); data_layout.addWidget(alt_label)
        self.alt_label = QLabel("高度 (Z): 0.0 m"); self.alt_label.setFont(data_font); data_layout.addWidget(self.alt_label)

        data_layout.addStretch()

    def calculate_altitude(self, pressure, sea_level_pressure):
        if pressure <= 0 or sea_level_pressure <= 0: return 0.0
        return 44330.0 * (1.0 - pow(pressure / sea_level_pressure, 0.1902949))

    def update_ui(self):
        data_packet = self.reader.get_latest_data()

        if data_packet is not None:
            # --- 1. 从数据包中解析数据 ---
            euler_angles = data_packet[0:3] # roll, pitch, yaw (单位: 度)
            accel = data_packet[3:6]
            gyro = data_packet[6:9]
            mag = data_packet[9:12]
            pressure = data_packet[12]

            # --- 2. 更新3D模型姿态 ---
            # 直接使用来自ESP32的、稳定可靠的欧拉角
            transform = pg.Transform3D()

            # --- 3. 更新高度 ---
            if self.initial_pressure is None and pressure > 800: self.initial_pressure = pressure
            if self.initial_pressure is not None: self.altitude = self.calculate_altitude(pressure, self.initial_pressure)
            transform.translate(0, 0, self.altitude / 10) # 应用高度

            # 应用旋转，注意旋转顺序通常很重要
            transform.rotate(euler_angles[2], 0, 0, 1) # 1. Yaw (绕Z轴)
            transform.rotate(euler_angles[1], 0, 1, 0) # 2. Pitch (绕Y轴)
            transform.rotate(euler_angles[0], 1, 0, 0) # 3. Roll (绕X轴)
            self.mesh.setTransform(transform)

            # --- 4. 更新UI文本标签 ---
            self.roll_label.setText(f"Roll:  {euler_angles[0]:>6.1f}°")
            self.pitch_label.setText(f"Pitch: {euler_angles[1]:>6.1f}°")
            self.yaw_label.setText(f"Yaw:   {euler_angles[2]:>6.1f}°")

            self.accel_label.setText(f"Acc (m/s²): {accel[0]:.1f}, {accel[1]:.1f}, {accel[2]:.1f}")
            self.gyro_label.setText(f"Gyro (rad/s): {gyro[0]:.1f}, {gyro[1]:.1f}, {gyro[2]:.1f}")
            self.mag_label.setText(f"Mag (uT):   {mag[0]:.0f}, {mag[1]:.0f}, {mag[2]:.0f}")
            self.pressure_label.setText(f"Pressure: {pressure:.1f} hPa")

            self.alt_label.setText(f"高度 (Z): {self.altitude:.2f} m")

    def closeEvent(self, event):
        self.reader.close()
        print("后台线程已停止，串口已关闭。程序退出。")
        event.accept()

if __name__ == '__main__':
    print("正在启动 ESP32 板载融合姿态可视化程序 (欧拉角模式)...")
    app = QApplication(sys.argv)
    reader = SerialDataReader(SERIAL_PORT, BAUD_RATE)
    visualizer = PoseVisualizer3D(reader)
    visualizer.show()
    sys.exit(app.exec())


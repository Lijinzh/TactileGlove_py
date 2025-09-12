# pose_estimator_6dof.py

import sys
import serial
import struct
import time
import numpy as np
from collections import deque
from dataclasses import dataclass
from threading import Thread, Lock

import pyqtgraph as pg
import pyqtgraph.opengl as gl
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont

# 导入 AHRS 库中的多种滤波器
from ahrs.filters import Madgwick, Mahony, EKF
from ahrs.common.orientation import q2R, q2euler

# --- 配置区 (Configuration Area) ---
SERIAL_PORT = 'COM10'
BAUD_RATE = 6000000

# =============================================================================
# [!!!] 核心调优参数区 (Core Tuning Parameters) [!!!]
# =============================================================================
# 1. 调试模式开关:
#    - 设置为 True: 启动命令行校准向导。
#    - 设置为 False: 正常启动3D可视化程序。
DEBUG_MODE = False

# 2. [新增] 是否使用磁力计 (Use Magnetometer):
#    - True:  9-axis融合, Yaw角稳定但易受磁场干扰。
#    - False: 6-axis融合, Yaw角会漂移但不受磁场干扰。
USE_MAGNETOMETER = True

# 3. 融合算法选择器:
#    - 在 'MADGWICK', 'MAHONY', 'EKF' 中选择一个。
FUSION_ALGORITHM = 'MADGWICK'

# 4. 各算法的参数:
# --- Madgwick ---
MADGWICK_GAIN = 3.0  # 推荐范围: 1.0 ~ 5.0。

# --- Mahony ---
MAHONY_KP = 1.0
MAHONY_KI = 0.05

# --- EKF (扩展卡尔曼滤波器) ---
EKF_NOISE_ACC = 0.1
EKF_NOISE_GYRO = 0.2
EKF_NOISE_MAG = 0.3

# 5. 磁力计偏置校准值 (仅在 USE_MAGNETOMETER = True 时有效):
MAG_BIAS = np.array([-18.90, 69.90, -68.70])
# =============================================================================

SENSOR_FREQUENCY = 250 # 估算的传感器发送频率(Hz)，用于滤波器初始化

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
    """在独立的后台线程中运行的串口读取器"""
    def __init__(self, port, baudrate):
        try:
            self.ser = serial.Serial(port, baudrate, timeout=0.1)
            print(f"成功打开串口 {port}")
        except serial.SerialException as e:
            print(f"错误：无法打开串口 {port}。请检查端口号或设备是否被占用。")
            print(e); sys.exit(1)
        self.buffer = bytearray()
        self.latest_data = None
        self.lock = Lock()
        self.running = False
        self.thread = None

    def _calculate_checksum(self, data_bytes: bytes) -> int:
        checksum = 0
        for byte in data_bytes: checksum ^= byte
        return checksum

    def _read_loop(self):
        while self.running:
            self.buffer.extend(self.ser.read(self.ser.in_waiting or 1))
            while len(self.buffer) >= PACKET_SIZE:
                header_index = self.buffer.find(bytes(PACKET_HEADER))
                if header_index == -1: self.buffer = self.buffer[-(PACKET_SIZE - 1):]; break
                if header_index > 0: self.buffer = self.buffer[header_index:]
                if len(self.buffer) < PACKET_SIZE: break
                packet_bytes = self.buffer[:PACKET_SIZE]
                self.buffer = self.buffer[PACKET_SIZE:]
                try:
                    *_, received_checksum = struct.unpack(PACKET_FORMAT, packet_bytes)
                    data_bytes_for_checksum = packet_bytes[2:-1]
                    if self._calculate_checksum(data_bytes_for_checksum) == received_checksum:
                        with self.lock:
                            self.latest_data = np.array(struct.unpack('<10f', packet_bytes[2:-1]))
                except struct.error: pass
            time.sleep(0.001)

    def start(self):
        if self.thread is None:
            self.running = True
            self.thread = Thread(target=self._read_loop, daemon=True)
            self.thread.start()
            print("后台串口读取线程已启动。")

    def get_latest_data(self) -> np.ndarray | None:
        with self.lock:
            data = self.latest_data
            self.latest_data = None
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
        mode_str = "9-Axis MARG" if USE_MAGNETOMETER else "6-Axis IMU"
        self.setWindowTitle(f'6-DOF 姿态实时解算 ({FUSION_ALGORITHM} / {mode_str})')
        self.setGeometry(100, 100, 1000, 800)

        # --- 初始化姿态估计算法 ---
        if FUSION_ALGORITHM == 'MADGWICK':
            self.fusion = Madgwick(frequency=SENSOR_FREQUENCY, gain=MADGWICK_GAIN)
        elif FUSION_ALGORITHM == 'MAHONY':
            self.fusion = Mahony(frequency=SENSOR_FREQUENCY, kp=MAHONY_KP, ki=MAHONY_KI)
        elif FUSION_ALGORITHM == 'EKF':
            self.fusion = EKF(frequency=SENSOR_FREQUENCY,
                              noise_acc=EKF_NOISE_ACC,
                              noise_gyro=EKF_NOISE_GYRO,
                              noise_mag=EKF_NOISE_MAG if USE_MAGNETOMETER else 0.0)
        else:
            raise ValueError("错误: 无效的融合算法选择! 请在 'MADGWICK', 'MAHONY', 'EKF' 中选择。")

        self.quaternion = np.array([1.0, 0.0, 0.0, 0.0])
        self.gyro_bias = np.array([0.0, 0.0, 0.0])

        self.altitude = 0.0
        self.initial_pressure = None

        self._setup_ui()
        self.reader.start()

        self._perform_gyro_calibration()

        self.timer = QTimer()
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.update_pose)
        self.timer.start()

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        self.view3d = gl.GLViewWidget()
        self.view3d.setCameraPosition(distance=5)
        main_layout.addWidget(self.view3d, stretch=3)

        grid = gl.GLGridItem(); grid.scale(2, 2, 1); self.view3d.addItem(grid)

        verts = np.array([ [0.5, 0.5, 0.5], [0.5, 0.5, -0.5], [0.5, -0.5, 0.5], [0.5, -0.5, -0.5], [-0.5, 0.5, 0.5], [-0.5, 0.5, -0.5], [-0.5, -0.5, 0.5], [-0.5, -0.5, -0.5] ]) * np.array([2.0, 1.0, 0.2])
        faces = np.array([ [0, 2, 3], [0, 3, 1], [4, 5, 7], [4, 7, 6], [0, 1, 5], [0, 5, 4], [2, 6, 7], [2, 7, 3], [1, 3, 7], [1, 7, 5], [0, 4, 6], [0, 6, 2] ])
        colors = np.array([ [1, 0, 0, 1], [1, 0.5, 0, 1], [1, 1, 0, 1], [0.5, 1, 0, 1], [0, 1, 0, 1], [0, 1, 0.5, 1], [0, 1, 1, 1], [0, 0.5, 1, 1] ])
        self.mesh = gl.GLMeshItem(vertexes=verts, faces=faces, vertexColors=colors, smooth=False, drawEdges=True)
        self.view3d.addItem(self.mesh)

        data_panel = QWidget(); data_layout = QVBoxLayout(data_panel); main_layout.addWidget(data_panel, stretch=1)
        title_font = QFont(); title_font.setPointSize(16); title_font.setBold(True)
        data_font = QFont(); data_font.setPointSize(14)
        info_font = QFont(); info_font.setPointSize(10)

        self.status_label = QLabel("正在初始化..."); self.status_label.setFont(title_font); data_layout.addWidget(self.status_label)
        data_layout.addSpacing(10)

        rot_label = QLabel("姿态 (欧拉角)"); rot_label.setFont(title_font); data_layout.addWidget(rot_label)
        self.roll_label = QLabel("Roll:  0.0°"); self.roll_label.setFont(data_font); data_layout.addWidget(self.roll_label)
        self.pitch_label = QLabel("Pitch: 0.0°"); self.pitch_label.setFont(data_font); data_layout.addWidget(self.pitch_label)
        self.yaw_label = QLabel("Yaw:   0.0°"); self.yaw_label.setFont(data_font); data_layout.addWidget(self.yaw_label)
        data_layout.addSpacing(20)

        q_label = QLabel("姿态 (四元数)"); q_label.setFont(title_font); data_layout.addWidget(q_label)
        self.q_w = QLabel("W: 1.0"); self.q_w.setFont(data_font); data_layout.addWidget(self.q_w)
        self.q_x = QLabel("X: 0.0"); self.q_x.setFont(data_font); data_layout.addWidget(self.q_x)
        self.q_y = QLabel("Y: 0.0"); self.q_y.setFont(data_font); data_layout.addWidget(self.q_y)
        self.q_z = QLabel("Z: 0.0"); self.q_z.setFont(data_font); data_layout.addWidget(self.q_z)
        data_layout.addSpacing(20)

        pos_label = QLabel("位置 (估算)"); pos_label.setFont(title_font); data_layout.addWidget(pos_label)
        self.alt_label = QLabel("高度 (Z): 0.0 m"); self.alt_label.setFont(data_font); data_layout.addWidget(self.alt_label)

        data_layout.addStretch()

        reset_label = QLabel("按 'R' 键重置姿态"); reset_label.setFont(info_font)
        data_layout.addWidget(reset_label)

    def _perform_gyro_calibration(self):
        self.status_label.setText("陀螺仪校准...")
        QApplication.processEvents()

        print("\n[陀螺仪校准] 请保持设备静止5秒钟...")

        gyro_samples = []
        start_time = time.time()
        while time.time() - start_time < 5:
            data = self.reader.get_latest_data()
            if data is not None: gyro_samples.append(data[3:6])
            time.sleep(0.01)

        if not gyro_samples:
            print("错误: 未能采集到陀螺仪数据进行校准!")
            self.status_label.setText("校准失败!")
            return

        self.gyro_bias = np.mean(gyro_samples, axis=0)
        print(f"陀螺仪校准完成。计算出的偏置 (rad/s):")
        print(f"X: {self.gyro_bias[0]:.4f}, Y: {self.gyro_bias[1]:.4f}, Z: {self.gyro_bias[2]:.4f}")

        mode_str = "9-Axis MARG" if USE_MAGNETOMETER else "6-Axis IMU"
        self.status_label.setText(f"运行中 ({FUSION_ALGORITHM} / {mode_str})")
        QApplication.processEvents()

    def calculate_altitude(self, pressure, sea_level_pressure):
        if pressure <= 0 or sea_level_pressure <= 0: return 0.0
        pressure_ratio = pressure / sea_level_pressure
        return 44330.0 * (1.0 - pow(pressure_ratio, 0.1902949))

    def update_pose(self):
        raw_data = self.reader.get_latest_data()

        if raw_data is not None:
            acc = raw_data[0:3]
            gyro = raw_data[3:6]
            mag = raw_data[6:9]
            pressure = raw_data[9]

            gyro_calibrated = gyro - self.gyro_bias

            acc_remapped = np.array([ acc[0], acc[1], acc[2]])
            gyro_remapped = np.array([ gyro_calibrated[0], gyro_calibrated[1], gyro_calibrated[2]])

            # --- [核心修改] 根据开关决定是否使用磁力计 ---
            if USE_MAGNETOMETER:
                mag_remapped = np.array([ mag[0], mag[1], mag[2]]) - MAG_BIAS
                if FUSION_ALGORITHM == 'MADGWICK':
                    self.quaternion = self.fusion.updateMARG(self.quaternion, gyro_remapped, acc_remapped, mag_remapped)
                else: # Mahony 和 EKF
                    self.quaternion = self.fusion.update(self.quaternion, gyro_remapped, acc_remapped, mag_remapped)
            else: # 不使用磁力计
                if FUSION_ALGORITHM == 'EKF':
                    self.quaternion = self.fusion.update(self.quaternion, gyro_remapped, acc_remapped)
                else: # Madgwick 和 Mahony
                    self.quaternion = self.fusion.updateIMU(self.quaternion, gyro_remapped, acc_remapped)

            # 高度计算
            if self.initial_pressure is None and pressure > 800: self.initial_pressure = pressure
            if self.initial_pressure is not None: self.altitude = self.calculate_altitude(pressure, self.initial_pressure)

            # 更新3D模型
            R = q2R(self.quaternion)
            transform = np.eye(4); transform[:3, :3] = R
            transform[2, 3] = self.altitude / 10
            self.mesh.setTransform(pg.Transform3D(*transform.flatten()))

            # 更新数据显示
            euler_angles = np.rad2deg(q2euler(self.quaternion))
            self.roll_label.setText(f"Roll:  {euler_angles[0]:>6.1f}°")
            self.pitch_label.setText(f"Pitch: {euler_angles[1]:>6.1f}°")
            self.yaw_label.setText(f"Yaw:   {euler_angles[2]:>6.1f}°")
            self.alt_label.setText(f"高度 (Z): {self.altitude:.2f} m")
            self.q_w.setText(f"W: {self.quaternion[0]:.3f}")
            self.q_x.setText(f"X: {self.quaternion[1]:.3f}")
            self.q_y.setText(f"Y: {self.quaternion[2]:.3f}")
            self.q_z.setText(f"Z: {self.quaternion[3]:.3f}")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_R:
            print("姿态已重置！")
            self.quaternion = np.array([1.0, 0.0, 0.0, 0.0])
            self.initial_pressure = None
            self._perform_gyro_calibration()

    def closeEvent(self, event):
        self.reader.close()
        print("后台线程已停止，串口已关闭。程序退出。")
        event.accept()

# 调试模式校准向导
def run_debug_mode():
    print("\n[ 校准向导已启动 ]")
    print("--------------------------------------------------")
    reader = SerialDataReader(SERIAL_PORT, BAUD_RATE)
    reader.start()

    # 步骤 1: 重力校准
    print("\n[步骤 1/2] 校准重力 (加速度计)")
    print("将你的PCB板水平、静止地放置在桌面上，等待5秒...")
    time.sleep(5)

    acc_samples = []
    print("正在采集数据...")
    for _ in range(50):
        d = reader.get_latest_data()
        if d is not None: acc_samples.append(d[0:3])
        time.sleep(0.02)

    if not acc_samples:
        print("错误：未能采集到加速度数据，请检查连接。"); reader.close(); return

    acc_avg = np.mean(acc_samples, axis=0)
    acc_remapped = np.array([acc_avg[0], acc_avg[1], acc_avg[2]])

    print(f"\n平均加速度读数 (重映射后): X={acc_remapped[0]:.2f}, Y={acc_remapped[1]:.2f}, Z={acc_remapped[2]:.2f}")
    if abs(acc_remapped[2]) > 9.0 and abs(acc_remapped[0]) < 2.0 and abs(acc_remapped[1]) < 2.0:
        print(">>> 重力校准成功！Z轴已对齐重力方向。")
    else:
        print(">>> 重力校准失败！请修改代码中 `run_debug_mode` 和 `update_pose` 内的坐标系重映射规则，然后重试。")
        reader.close(); return

    # [核心修改] 只有在启用磁力计时才进行校准
    if not USE_MAGNETOMETER:
        print("\n--------------------------------------------------")
        print("\n磁力计已禁用。校准完成。")
        print("请将 `DEBUG_MODE` 设置为 `False` 以启动3D可视化。")
        reader.close()
        return

    # 步骤 2: 磁力计偏置校准
    print("\n--------------------------------------------------")
    print("\n[步骤 2/2] 校准磁场 (磁力计)")
    print("现在，请拿起你的设备，在空中随意地、缓慢地画8字形或朝向各个方向旋转。")
    print("目标是让传感器经历尽可能多的朝向。持续大约20-30秒。")
    input("准备好后，请按 Enter 键开始采集...")

    mag_min = np.array([np.inf, np.inf, np.inf]); mag_max = np.array([-np.inf, -np.inf, -np.inf])

    start_time = time.time()
    print("开始采集磁力计数据...")
    try:
        while time.time() - start_time < 25:
            raw_data = reader.get_latest_data()
            if raw_data is not None:
                mag = raw_data[6:9]
                mag_remapped = np.array([mag[0], mag[1], mag[2]])
                mag_min = np.minimum(mag_min, mag_remapped)
                mag_max = np.maximum(mag_max, mag_remapped)
                print(f"\r采集中... X:[{mag_min[0]:.1f}, {mag_max[0]:.1f}] Y:[{mag_min[1]:.1f}, {mag_max[1]:.1f}] Z:[{mag_min[2]:.1f}, {mag_max[2]:.1f}]", end="")
            time.sleep(0.02)
    except KeyboardInterrupt: pass
    finally: print("\n采集结束。")

    mag_bias = (mag_max + mag_min) / 2.0
    print("\n[ 校准完成! ]")
    print("--------------------------------------------------")
    print("请将以下计算出的偏置值，复制并粘贴到代码顶部的 `MAG_BIAS` 变量中：")
    print(f"\nMAG_BIAS = np.array([{mag_bias[0]:.2f}, {mag_bias[1]:.2f}, {mag_bias[2]:.2f}])\n")
    print("完成修改后，请将代码顶部的 `DEBUG_MODE` 设置为 `False`，然后重新运行脚本以启动3D可视化。")
    reader.close()


if __name__ == '__main__':
    if DEBUG_MODE:
        run_debug_mode()
    else:
        print("正在启动6-DOF姿态解算与可视化程序...")
        app = QApplication(sys.argv)
        reader = SerialDataReader(SERIAL_PORT, BAUD_RATE)
        visualizer = PoseVisualizer3D(reader)
        visualizer.show()
        sys.exit(app.exec())


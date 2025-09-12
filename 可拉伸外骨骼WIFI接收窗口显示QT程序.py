import socket
import struct
import numpy as np
import time
from collections import deque
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QLabel, QTableWidget, QTableWidgetItem)
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QColor

# 必须与ESP32代码中的定义一致！
ROWS = 6   # 数组行数
COLS = 4   # 数组列数
MAX_VALUE = 3300  # 数据最大值

class SimpleTactileDisplay(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("可拉伸外骨骼触觉数据")
        self.setGeometry(100, 100, 800, 600)

        # 主界面布局
        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.layout = QVBoxLayout()
        self.main_widget.setLayout(self.layout)

        # 状态标签
        self.status_label = QLabel("等待连接...")
        self.layout.addWidget(self.status_label)

        # FPS显示
        self.fps_label = QLabel("FPS: 0.0")
        self.layout.addWidget(self.fps_label)

        # 数据表格
        self.table = QTableWidget(ROWS, COLS)
        self.table.setHorizontalHeaderLabels([f"列 {i}" for i in range(COLS)])
        self.table.setVerticalHeaderLabels([f"行 {i}" for i in range(ROWS)])

        # 设置表格样式
        self.table.setStyleSheet("""
            QTableWidget {
                font-size: 14px;
                font-family: Arial;
            }
            QTableWidget::item {
                padding: 5px;
                text-align: center;
            }
        """)

        # 设置列宽
        for j in range(COLS):
            self.table.setColumnWidth(j, 100)

        self.layout.addWidget(self.table)

        # 数据缓冲区
        self.buffer = bytearray()
        self.fps_tracker = deque(maxlen=30)
        self.current_data = np.zeros((ROWS, COLS))

        # 定时器
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_display)
        self.timer.start(50)  # 20Hz刷新

        # 网络连接
        self.socket = None
        self.connect_to_esp32()

    def connect_to_esp32(self):
        HOST, PORT = '0.0.0.0', 8888
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.socket.bind((HOST, PORT))
            self.socket.listen(1)
            self.status_label.setText(f"监听 {HOST}:{PORT}...")

            # 异步接受连接
            QTimer.singleShot(100, self.accept_connection)
        except Exception as e:
            self.status_label.setText(f"连接错误: {str(e)}")

    def accept_connection(self):
        try:
            conn, addr = self.socket.accept()
            self.conn = conn
            self.status_label.setText(f"已连接: {addr[0]}:{addr[1]}")
            # 开始接收数据
            QTimer.singleShot(0, self.receive_data)
        except Exception as e:
            self.status_label.setText(f"接受连接错误: {str(e)}")

    def receive_data(self):
        try:
            data = self.conn.recv(4096)
            if not data:
                self.status_label.setText("连接已关闭")
                return

            self.buffer.extend(data)

            while True:
                frame = self.extract_frame()
                if frame is None:
                    break

                self.current_data = frame
                current_time = time.time()
                self.fps_tracker.append(current_time)

            # 继续接收数据
            QTimer.singleShot(0, self.receive_data)
        except Exception as e:
            self.status_label.setText(f"接收错误: {str(e)}")

    def extract_frame(self):
        start = self.buffer.find(b'\xAA')
        if start == -1:
            return None

        if len(self.buffer) < start + 3:
            return None

        data_len = struct.unpack('<H', self.buffer[start+1:start+3])[0]
        total_len = 3 + data_len + 1

        if len(self.buffer) < start + total_len:
            return None

        if self.buffer[start + total_len - 1] != 0x55:
            print("帧尾错误!")
            del self.buffer[:start + total_len]
            return None

        data = self.buffer[start+3:start+3+data_len]
        del self.buffer[:start + total_len]

        arr = np.frombuffer(data, dtype=np.float32).reshape((ROWS, COLS))
        return arr

    def get_fps(self):
        if len(self.fps_tracker) < 2:
            return 0
        time_diff = self.fps_tracker[-1] - self.fps_tracker[0]
        if time_diff <= 0:
            return 0
        return (len(self.fps_tracker) - 1) / time_diff

    def update_display(self):
        # 更新FPS
        fps = self.get_fps()
        self.fps_label.setText(f"FPS: {fps:.1f}")

        # 更新表格数据
        for i in range(ROWS):
            for j in range(COLS):
                value = self.current_data[i, j]
                item = QTableWidgetItem(f"{int(value)}")  # 显示整数值
                item.setTextAlignment(0x0004 | 0x0080)  # 居中对齐

                # 根据数值设置背景色 (浅色渐变)
                normalized = min(1.0, max(0.0, value / MAX_VALUE))
                red = int(255 * normalized)
                green = int(255 * (1 - normalized))
                blue = 150  # 固定蓝色分量使颜色更柔和
                item.setBackground(QColor(red, green, blue))

                # 根据背景色自动选择文字颜色
                if normalized > 0.7:
                    item.setForeground(QColor(255, 255, 255))  # 深色背景用白色文字
                else:
                    item.setForeground(QColor(0, 0, 0))  # 浅色背景用黑色文字

                self.table.setItem(i, j, item)

    def closeEvent(self, event):
        if hasattr(self, 'conn'):
            self.conn.close()
        if hasattr(self, 'socket'):
            self.socket.close()
        event.accept()

if __name__ == "__main__":
    app = QApplication([])
    window = SimpleTactileDisplay()
    window.show()
    app.exec_()

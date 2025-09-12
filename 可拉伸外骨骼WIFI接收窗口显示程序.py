import socket
import struct
import numpy as np
import time
from collections import deque
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# 必须与ESP32代码中的定义一致！
ROWS = 6   # 数组行数
COLS = 4   # 数组列数

class HighSpeedReceiver:
    def __init__(self):
        self.buffer = bytearray()
        self.fps_tracker = deque(maxlen=30)
        # 初始化可视化
        self.fig, self.ax = plt.subplots()
        self.cax = None
        self.data = np.zeros((ROWS, COLS))  # 初始化数据
        self.last_update_time = time.time()

    def receive(self, sock):
        try:
            data = sock.recv(4096)
            if not data:
                return None
            self.buffer.extend(data)

            frames = []
            while True:
                frame = self._extract_frame()
                if frame is None:
                    break
                frames.append(frame)
                current_time = time.time()
                self.fps_tracker.append(current_time)
                # 确保至少有2个时间点才能计算FPS
                if len(self.fps_tracker) > 1:
                    time_diff = current_time - self.last_update_time
                    if time_diff > 0.1:  # 至少0.1秒更新一次显示
                        self.last_update_time = current_time
            return frames
        except Exception as e:
            print(f"Receive error: {e}")
            return None

    def _extract_frame(self):
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
            print("Frame tail error!")
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

    def update_plot(self, frame):
        if self.cax is None:
            # 第一次调用时创建热力图
            self.cax = self.ax.imshow(self.data, cmap='viridis', interpolation='nearest')
            plt.colorbar(self.cax)
            self.ax.set_title("Real-time 6x4 Array Visualization")
            self.ax.set_xticks(np.arange(COLS))
            self.ax.set_yticks(np.arange(ROWS))
            self.ax.set_xticklabels([f"Col {i}" for i in range(COLS)])
            self.ax.set_yticklabels([f"Row {i}" for i in range(ROWS)])

            # 添加数值显示
            for i in range(ROWS):
                for j in range(COLS):
                    self.ax.text(j, i, f"{self.data[i, j]:.2f}", ha="center", va="center", color="w")
        else:
            # 更新热力图数据
            self.cax.set_array(self.data)

            # 清除旧文本
            for txt in self.ax.texts:
                txt.remove()

            # 添加新数值
            for i in range(ROWS):
                for j in range(COLS):
                    self.ax.text(j, i, f"{self.data[i, j]:.2f}", ha="center", va="center", color="w")

        return self.cax,

if __name__ == "__main__":
    HOST, PORT = '0.0.0.0', 8888
    receiver = HighSpeedReceiver()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.bind((HOST, PORT))
        s.listen()
        print(f"Listening on {HOST}:{PORT}...")
        conn, addr = s.accept()
        print(f"Connected by {addr}")

        # 创建动画
        ani = FuncAnimation(receiver.fig, receiver.update_plot, interval=50, blit=False)
        plt.show(block=False)  # 非阻塞显示

        try:
            while True:
                frames = receiver.receive(conn)
                if frames is not None:
                    receiver.data = frames[-1]  # 更新最新数据
                    fps = receiver.get_fps()
                    receiver.fig.suptitle(f"FPS: {fps:.1f}")
                    plt.pause(0.01)  # 允许GUI更新
        except KeyboardInterrupt:
            print("\nStopped.")
            plt.close()

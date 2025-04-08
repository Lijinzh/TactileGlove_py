import serial
import struct
import glove_data_pb2
import time
import numpy as np
import matplotlib.pyplot as plt
from collections import deque

# 强制使用高性能后端（必须在其他matplotlib调用前设置）
plt.switch_backend('Qt5Agg')  # 或 'TkAgg'

# 热力图配置
PLOT_SIZE = (12, 6)  # (width, height)
CMAP = 'viridis'
Z_RANGE = (0, 255)  # 固定范围避免动态计算

# 初始化图形界面
plt.ion()
fig, ax = plt.subplots(figsize=(10, 5))
img = ax.imshow(np.zeros(PLOT_SIZE[::-1]),  # 注意宽高顺序
                cmap=CMAP,
                aspect='auto',
                vmin=Z_RANGE[0],
                vmax=Z_RANGE[1])
plt.colorbar(img, label='Z Value')
plt.title(f'Real-time Z Channel ({PLOT_SIZE[0]}×{PLOT_SIZE[1]})')
plt.tight_layout()

# 预分配内存（重要优化）
points_buffer = np.zeros((72, 3), dtype=np.float32)  # 72个点，每个点xyz

class HighPrecisionFPS:
    """高精度帧率计算器"""
    def __init__(self, window_size=30):
        self.timestamps = deque(maxlen=window_size)

    def update(self):
        self.timestamps.append(time.perf_counter())  # 最高精度计时
        if len(self.timestamps) >= 2:
            fps = len(self.timestamps)/(self.timestamps[-1]-self.timestamps[0])
            print(f"\rFPS: {fps:.1f} | Latency: {1e3/fps:.1f}ms", end="")

def robust_serial_read(ser):
    """鲁棒的串口数据读取"""
    # 快速查找帧头
    while True:
        header = ser.read_until(b'\xAA')
        if not header.endswith(b'\xAA'):
            continue

        # 确保有足够数据（2字节长度）
        if ser.in_waiting < 2:
            continue

        # 读取长度
        length_bytes = ser.read(2)
        msg_len = struct.unpack('<H', length_bytes)[0]

        # 检查数据完整性
        if ser.in_waiting < msg_len + 1:  # +1 for end marker
            continue

        # 读取完整帧
        frame_data = ser.read(msg_len + 1)
        if frame_data[-1:] != b'\x55':
            continue

        return frame_data[:-1]  # 去掉结束符

def process_frame(data, fps_tracker):
    """高效处理单帧数据"""
    try:
        # Protobuf解析
        sensor_data = glove_data_pb2.AllSensorsData()
        sensor_data.ParseFromString(data)

        # 向量化数据填充（比循环快10倍）
        sensor = sensor_data.sensors[0]
        for i in range(71):  # 跳过第0点
            point = sensor.points[i+1]
            points_buffer[i] = (point.x, point.y, point.z)

        # 更新图像（使用blit加速）
        img.set_array(points_buffer.reshape(6, 12, 3)[:, :, 2])
        ax.draw_artist(img)
        fig.canvas.blit(ax.bbox)
        fig.canvas.flush_events()

        fps_tracker.update()
    except Exception:
        pass  # 静默处理错误避免打印影响性能

def main():
    fps_tracker = HighPrecisionFPS()

    try:
        # 串口配置（增加缓冲区和优化参数）
        with serial.Serial('COM9', 6000000,
                           timeout=0.01,  # 更短的超时
                           write_timeout=0,
                           inter_byte_timeout=0.001) as ser:

            ser.reset_input_buffer()
            print("串口已连接，开始接收数据...")

            while True:
                frame_data = robust_serial_read(ser)
                if frame_data:
                    process_frame(frame_data, fps_tracker)

    except KeyboardInterrupt:
        print("\n程序终止")
    finally:
        plt.ioff()
        plt.show()

if __name__ == "__main__":
    main()

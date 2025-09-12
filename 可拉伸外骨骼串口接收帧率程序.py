import serial
import struct
import time
from collections import deque

class FrameRateTracker:
    def __init__(self, window_size=10):
        self.timestamps = deque(maxlen=window_size)  # 存储最近的时间戳

    def update(self):
        """记录新帧的时间戳"""
        self.timestamps.append(time.time())

    def get_fps(self):
        """计算当前帧率（FPS）"""
        if len(self.timestamps) < 2:
            return 0.0
        time_diff = self.timestamps[-1] - self.timestamps[0]
        if time_diff <= 0:
            return 0.0
        return (len(self.timestamps) - 1) / time_diff

def receive_data(serial_port, frame_rate_tracker):
    # 等待帧头 0xAA
    while True:
        start_byte = serial_port.read(1)
        if start_byte == b'\xAA':
            break

    # 读取数据长度（2字节，小端序）
    length_bytes = serial_port.read(2)
    data_length = struct.unpack('<H', length_bytes)[0]

    # 计算数据点数量（6×4=24个double）
    num_doubles = data_length // 8  # 每个double占8字节

    # 读取数据内容
    data_bytes = serial_port.read(data_length)

    # 检查帧尾 0x55
    end_byte = serial_port.read(1)
    if end_byte != b'\x55':
        print("帧结束标记错误！")
        return None

    # 更新帧率统计
    frame_rate_tracker.update()

    # 解析数据为 6×4 的二维数组
    try:
        flat_data = struct.unpack(f'<{num_doubles}d', data_bytes)
        mv_values = []
        for i in range(0, num_doubles, 4):
            row = flat_data[i:i+4]
            mv_values.append(row)
        return mv_values
    except Exception as e:
        print(f"数据解析失败: {str(e)}")
        return None

# 使用示例
if __name__ == "__main__":
    # 配置串口（根据实际情况修改）
    ser = serial.Serial(
        port='COM10',      # 串口号
        baudrate=6000000,  # 波特率
        timeout=1         # 超时时间(秒)
    )

    # 初始化帧率统计器（窗口大小=10，计算最近10帧的FPS）
    fps_tracker = FrameRateTracker(window_size=10)

    try:
        while True:
            data = receive_data(ser, fps_tracker)
            if data is not None:
                # 打印当前帧率（FPS）
                fps = fps_tracker.get_fps()
                print(f"\r接收帧率: {fps:.2f} FPS | 最新数据:", end="")
                for row in data:
                    print(row, end=" ")
                print("", end="", flush=True)
    except KeyboardInterrupt:
        print("\n程序终止")
    finally:
        ser.close()

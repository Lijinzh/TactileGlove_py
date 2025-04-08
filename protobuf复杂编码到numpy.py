import serial
import struct
import traceback
import glove_data_pb2
import time
import numpy as np
import matplotlib.pyplot as plt

# 初始化交互模式
plt.ion()
fig, ax = plt.subplots(figsize=(12, 6))
img = ax.imshow(np.zeros((6, 12)), cmap='viridis', aspect='auto')  # 单通道热力图
plt.colorbar(img, label='Z Value')  # 添加颜色条
plt.title('Real-time Z Channel (12×6)')
plt.axis('on')  # 显示坐标轴（可选）
img.set_clim(0, 255)  # 根据实际范围调整


def hex_dump(data, max_bytes=100):
    return ' '.join([f'{byte:02x}' for byte in data[:max_bytes]]) + \
        (f'... (total {len(data)} bytes)' if len(data) > max_bytes else '')


class FrameRateTracker:
    def __init__(self, print_interval=1.0):
        self.frame_count = 0
        self.last_print_time = time.time()
        self.print_interval = print_interval

    def increment(self):
        self.frame_count += 1
        current_time = time.time()

        # 每隔指定时间打印帧率
        if current_time - self.last_print_time >= self.print_interval:
            frame_rate = self.frame_count / (current_time - self.last_print_time)
            print(f"帧率: {frame_rate:.2f} FPS")

            # 重置计数器
            self.frame_count = 0
            self.last_print_time = current_time


def receive_protobuf_data(serial_port, frame_rate_tracker):
    # 等待帧开始标记
    while True:
        start_byte = serial_port.read(1)
        if start_byte == b'\xAA':
            break

            # 读取消息长度（2字节，小端序）
    length_bytes = serial_port.read(2)
    message_length = struct.unpack('<H', length_bytes)[0]
    # print(message_length)

    # 读取消息内容
    message_data = serial_port.read(message_length)

    # 读取帧结束标记
    end_byte = serial_port.read(1)
    if end_byte != b'\x55':
        print("帧结束标记错误!")
        return

        # Protobuf 解析
    try:
        all_sensors_data = glove_data_pb2.AllSensorsData()
        all_sensors_data.ParseFromString(message_data)

        # 增加帧计数
        frame_rate_tracker.increment()

        # 打印传感器数据
        print_sensor_data(all_sensors_data)

    except Exception as parse_error:
        print("Protobuf 解析失败:")
        print(str(parse_error))
        print(traceback.format_exc())


def print_sensor_data(all_sensors_data):
    global img, fig  # 假设这些是全局变量
    # 快速提取数据（跳过不必要的循环和类型转换）
    sensor = all_sensors_data.sensors[0]  # 直接取第一个传感器
    points_data = np.empty((72, 3), dtype=np.float32)  # 预分配内存
    # 一次性填充数据（避免逐点append）
    for i, point in enumerate(sensor.points[1:]):  # 跳过第0点
        points_data[i, 0] = point.x
        points_data[i, 1] = point.y
        points_data[i, 2] = point.z
    # 重塑并提取Z通道（避免中间变量）
    z_data = points_data.reshape(6, 12, 3)[:, :, 2]  # 直接得到 (6, 12)
    # 更新图像（禁用自动缩放以加速）
    img.set_data(z_data)
    img.set_clim(z_data.min(), z_data.max())  # 固定范围可进一步提速
    fig.canvas.flush_events()
    # 可选：降低plt.pause的间隔（但可能影响其他进程）
    # plt.pause(0.0001)  # 极短暂停（慎用）


def main():
    # 创建帧率追踪器
    frame_rate_tracker = FrameRateTracker()

    # 使用高波特率
    try:
        with serial.Serial('/dev/ttyACM1', 6000000, timeout=2) as ser:
            while True:
                receive_protobuf_data(ser, frame_rate_tracker)

    except serial.SerialException as e:
        print("串口异常:", str(e))
    except KeyboardInterrupt:
        print("\n程序已终止，正在关闭串口...")
    except Exception as e:
        print("发生了一个未知错误:", str(e))
        print(traceback.format_exc())
    except KeyboardInterrupt:
        plt.ioff()
        plt.show()  # 退出时保留最终图像


if __name__ == "__main__":
    main()

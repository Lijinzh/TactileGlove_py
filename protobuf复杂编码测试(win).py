import serial
import struct
import traceback
import glove_data_pb2
import time


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
    print(f"传感器数量: {len(all_sensors_data.sensors)}")

    for sensor_idx, sensor in enumerate(all_sensors_data.sensors):
        print(f"传感器 {sensor_idx + 1}:")
        print(f"  点数: {len(sensor.points)}")

        # 预览第一个点
        if sensor.points:
            point = sensor.points[0]
            print(f"    点 0: x={point.x}, y={point.y}, z={point.z}")


def main():
    # 创建帧率追踪器
    frame_rate_tracker = FrameRateTracker()

    # 使用高波特率
    try:
        with serial.Serial('COM9', 6000000, timeout=2) as ser:
            while True:
                receive_protobuf_data(ser, frame_rate_tracker)

    except serial.SerialException as e:
        print("串口异常:", str(e))
    except KeyboardInterrupt:
        print("\n程序已终止，正在关闭串口...")
    except Exception as e:
        print("发生了一个未知错误:", str(e))
        print(traceback.format_exc())


if __name__ == "__main__":
    main()

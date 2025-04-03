import time
import struct
import serial
import glove_data_pb2  # 这里假设生成的Python文件里包含Point3D


def main():
    ser = serial.Serial('/dev/ttyACM1', baudrate=115200, timeout=1)

    # 用于统计帧数的计数器及上次打印的时间
    frames_count = 0
    last_print_time = time.time()

    while True:
        # 1) 读取2字节长度信息
        length_bytes = ser.read(2)
        if len(length_bytes) < 2:
            # 未读满2字节，可能还没数据或等待数据中
            continue

            # 2) 解包出这一帧的长度 frame_length
        frame_length = struct.unpack('<H', length_bytes)[0]

        # 3) 读取 frame_length 长度的实际数据
        frame_data = ser.read(frame_length)
        if len(frame_data) < frame_length:
            # 如果数据没读够，说明本次还不完整，跳过
            continue

            # 4) 尝试解析Protobuf数据
        try:
            point = glove_data_pb2.Point3D()
            point.ParseFromString(frame_data)

            # 成功解析到一帧，累加计数
            frames_count += 1

        except Exception as e:
            print("Parse error:", e)

            # 5) 统计时间，判断是否已到1秒周期
        now = time.time()
        if now - last_print_time >= 1.0:
            # 过去这1秒接收的帧数
            elapsed = now - last_print_time
            avg_fps = frames_count / elapsed

            print(f"每秒接收帧数: {frames_count}, 平均帧率: {avg_fps:.2f} FPS")

            # 重置计数器与时间
            frames_count = 0
            last_print_time = now


if __name__ == '__main__':
    main()

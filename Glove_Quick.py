import serial
import struct
import time

# 配置串口
serial_port = '/dev/ttyACM1'  # 根据实际的串口号修改
baud_rate = 2000000     # 波特率与Arduino一致

# 定义头尾标识符
HEADER = b'\xAA'  # 头标识符
FOOTER = b'\x55'  # 尾标识符

BUFFER_LIMIT = 1024    # 设置缓冲区最大容量（字节）
CLEANUP_TIMEOUT = 5    # 清理超时时间（秒）

# 统计接收到的完整数据包数量
packet_count = 0
start_time = time.time()  # 记录开始时间

try:
    with serial.Serial(serial_port, baud_rate, timeout=1) as ser:
        print("等待接收数据...")
        buffer = b""  # 用于存储接收的字节数据
        last_read_time = time.time()  # 记录上次读取时间

        while True:
            if ser.in_waiting > 0:  # 确保有数据可读取
                buffer += ser.read(ser.in_waiting)  # 读取所有可用数据
                last_read_time = time.time()  # 更新时间戳

                # 检查是否接收到完整消息
                while True:
                    header_index = buffer.find(HEADER)  # 查找头标识符
                    footer_index = buffer.find(FOOTER)  # 查找尾标识符

                    # 确定数据的完整性
                    if header_index != -1 and footer_index > header_index:
                        # 提取有效数据
                        data_start = header_index + len(HEADER)  # 数据开始位置
                        data_end = footer_index  # 数据结束位置
                        data = buffer[data_start:data_end]  # 从缓冲区提取有效数据

                        # 解析整数数据
                        integers = []
                        num_ints = len(data) // 4  # 计算整数的数量

                        for i in range(num_ints):
                            integer = struct.unpack('<i', data[i * 4:(i + 1) * 4])[0]
                            integers.append(integer)

                            # 打印接收到的整数数组
                        print(integers)

                        # 更新数据包计数
                        packet_count += 1

                        # 清空缓冲区
                        buffer = buffer[footer_index + len(FOOTER):]  # 剩余的数据
                    else:
                        break  # 继续读取更多的数据

            # 清理缓冲区逻辑
            if time.time() - last_read_time > CLEANUP_TIMEOUT:
                print("缓冲区超时，清理数据...")
                buffer = b""  # 清空缓冲区
                last_read_time = time.time()  # 重新更新时间戳

            # 超过缓冲区限制
            if len(buffer) > BUFFER_LIMIT:
                print("缓冲区溢出，清理数据...")
                buffer = b""  # 清空缓冲区
                last_read_time = time.time()  # 重新更新时间戳

            # 打印帧率
            current_time = time.time()
            if current_time - start_time >= 1.0:  # 每秒打印一次帧率
                print(f"每秒接收到的帧数: {packet_count}")  # 打印帧率
                packet_count = 0  # 重置计数
                start_time = current_time  # 重置开始时间

except serial.SerialException as e:
    print(f"串口错误: {e}")
except Exception as e:
    print(f"发生错误: {e}")
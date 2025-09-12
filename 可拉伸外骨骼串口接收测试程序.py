import serial
import struct

def receive_data(serial_port):
    # 等待帧头 0xAA
    while True:
        start_byte = serial_port.read(1)
        if start_byte == b'\xAA':
            break

    # 读取数据长度（2字节，小端序）
    length_bytes = serial_port.read(2)
    data_length = struct.unpack('<H', length_bytes)[0]  # 无符号短整型

    # 计算数据点数量（6×4=24个double）
    num_doubles = data_length // 8  # 每个double占8字节

    # 读取数据内容
    data_bytes = serial_port.read(data_length)

    # 检查帧尾 0x55
    end_byte = serial_port.read(1)
    if end_byte != b'\x55':
        print("帧结束标记错误！")
        return None

    # 解析数据为 6×4 的二维数组
    try:
        # 先解包成一维数组（24个double）
        flat_data = struct.unpack(f'<{num_doubles}d', data_bytes)

        # 转换为 6×4 的二维数组
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

    try:
        while True:
            data = receive_data(ser)
            if data is not None:
                print("接收到的数据:")
                for row in data:
                    print(row)
    except KeyboardInterrupt:
        print("程序终止")
    finally:
        ser.close()

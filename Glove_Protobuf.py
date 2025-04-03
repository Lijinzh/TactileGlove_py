import serial
import struct
import numpy as np

# 设置串口号和波特率
ser = serial.Serial('/dev/ttyACM1', 115200)  # 替换为你的串口号
ser.flush()

NUM_3D_SENSORS = 5
NUM_1D_SENSORS = 20
NUM_3D_POINTS = 73

while True:
    # 每次接收 5*73*(3*4) + 20*4 字节的数据
    num_bytes = NUM_3D_SENSORS * NUM_3D_POINTS * 3 * 4 + NUM_1D_SENSORS * 4
    raw_data = ser.read(num_bytes)  # 读取指定数量的字节

    if len(raw_data) == num_bytes:
        # 解码三维传感器数据
        sensor_3d_data = np.frombuffer(raw_data[:NUM_3D_SENSORS * NUM_3D_POINTS * 3 * 4], dtype=np.float32).reshape((NUM_3D_SENSORS, NUM_3D_POINTS, 3))

        # 解码一维传感器数据
        sensor_1d_data = np.frombuffer(raw_data[NUM_3D_SENSORS * NUM_3D_POINTS * 3 * 4:], dtype=np.float32)
        print("1")
        print("2")

        # print("3D Sensor Data:", sensor_3d_data)
        # print("1D Sensor Data:", sensor_1d_data)
    else:
        print("接收到错误长度的数据")
import serial
import struct
import glove_data_pb2
import numpy as np
import matplotlib.pyplot as plt
import threading

# 全局变量
latest_z_data = np.random.rand(6, 12) * 100  # 初始随机数据（测试用）
running = True

# 初始化图形（更简单的设置）
plt.ion()
fig, ax = plt.subplots()
img = ax.imshow(latest_z_data, cmap='hot', vmin=0, vmax=255)  # 强制设置颜色范围
plt.colorbar(img)
plt.title('Pressure Map')


def serial_worker(port):
    global latest_z_data
    try:
        while running:
            # 简化的数据读取逻辑
            if port.read(1) == b'\xAA':
                length = struct.unpack('<H', port.read(2))[0]
                data = port.read(length)
                if port.read(1) == b'\x55':
                    sensor_data = glove_data_pb2.AllSensorsData()
                    sensor_data.ParseFromString(data)

                    # 直接硬编码提取数据（假设第一个传感器）
                    points = sensor_data.sensors[0].points
                    z_values = [p.z for p in points[1:]]  # 跳过第一个点
                    latest_z_data = np.array(z_values).reshape(6, 12)
    except Exception as e:
        print(f"串口错误: {e}")


def display_worker():
    global running
    while running:
        img.set_data(latest_z_data)
        img.autoscale()  # 强制自动缩放
        fig.canvas.draw_idle()  # 更高效的刷新方式
        fig.canvas.flush_events()
        plt.pause(0.01)  # 必须的暂停


def main():
    global running
    try:
        with serial.Serial('/dev/ttyACM1', 6000000, timeout=1) as ser:
            print("串口已连接，开始接收数据...")

            # 启动线程
            threading.Thread(target=serial_worker, args=(ser,), daemon=True).start()
            display_worker()  # 直接在主线程运行显示（简化）

    except KeyboardInterrupt:
        print("正在停止...")
    finally:
        running = False
        plt.ioff()
        plt.show()


if __name__ == "__main__":
    main()

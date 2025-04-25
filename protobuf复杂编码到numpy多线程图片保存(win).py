import serial
import struct
import glove_data_pb2
import numpy as np
import matplotlib.pyplot as plt
import threading
import os
import time

# 全局变量
latest_z_data = np.zeros((6, 12), dtype=np.uint8)
running = True

# 初始化图形
plt.ion()
fig, ax = plt.subplots()
img = ax.imshow(latest_z_data, cmap='hot', vmin=0, vmax=15)
plt.colorbar(img)
plt.title('Pressure Map')

def save_raw_data():
    """直接保存数据数组为PNG，不显示任何窗口"""
    # 确保目录存在
    os.makedirs("raw_data_images", exist_ok=True)
    filename = f"raw_data_images/data_{int(time.time())}.png"

    # 关键修改：使用agg后端直接保存（不弹窗）
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    # 创建内存中的figure
    fig = Figure(figsize=(12, 6), frameon=False)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis('off')
    ax.imshow(latest_z_data, cmap='binary', vmin=0, vmax=255)

    # 直接保存到文件
    canvas = FigureCanvasAgg(fig)
    canvas.print_png(filename)
    print(f"已静默保存原始数据到: {filename}")

def serial_worker(port):
    global latest_z_data
    try:
        while running:
            if port.read(1) == b'\xAA':
                length = struct.unpack('<H', port.read(2))[0]
                data = port.read(length)
                if port.read(1) == b'\x55':
                    sensor_data = glove_data_pb2.AllSensorsData()
                    sensor_data.ParseFromString(data)
                    z_values = [p.z for p in sensor_data.sensors[0].points[1:]]
                    latest_z_data = np.clip(np.array(z_values).reshape(6, 12), 0, 255).astype(np.uint8)
    except Exception as e:
        print(f"串口错误: {e}")

def display_worker():
    while running:
        img.set_data(latest_z_data)
        fig.canvas.draw_idle()
        fig.canvas.flush_events()
        plt.pause(0.01)

def main():
    global running
    try:
        with serial.Serial('COM9', 6000000, timeout=1) as ser:
            print("串口已连接 | 按 [X] 保存数据（无弹窗） | Ctrl+C 停止")

            def on_key(event):
                if event.key.lower() == 'x':
                    save_raw_data()
            fig.canvas.mpl_connect('key_press_event', on_key)

            threading.Thread(target=serial_worker, args=(ser,), daemon=True).start()
            display_worker()

    except KeyboardInterrupt:
        print("正在停止...")
    finally:
        running = False
        plt.ioff()

if __name__ == "__main__":
    main()

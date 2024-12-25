import serial
import struct
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import time

# 设置串口参数
ser = serial.Serial('COM5', 115200, timeout=0.01)  # 请将 'COM3' 替换为您的实际串口号
# ser = serial.Serial('COM7', 115200, timeout=0.01)  # 请将 'COM3' 替换为您的实际串口号

num_rows = 6
num_cols = 6
data_length = num_rows * num_cols
# 计数器和时间记录变量
frame_count = 0
start_time = time.time()


def read_data():
    global frame_count, start_time  # 使用全局变量
    while True:
        header = ser.read(2)
        if len(header) < 2:
            return None
        if header[0] == 0xAA and header[1] == 0xBB:
            data_bytes = ser.read(data_length * 2)
            if len(data_bytes) < data_length * 2:
                return None
            footer = ser.read(2)
            if len(footer) < 2:
                return None
            if footer[0] == 0xCC and footer[1] == 0xDD:
                values = []
                for i in range(0, len(data_bytes), 2):
                    high = data_bytes[i]
                    low = data_bytes[i + 1]
                    value = (high << 8) | low
                    values.append(value)
                matrix = np.array(values).reshape((num_rows, num_cols))
                # 更新帧计数并计算帧率
                frame_count += 1
                elapsed_time = time.time() - start_time
                if elapsed_time > 1:  # 每秒计算一次帧率
                    frame_rate = frame_count / elapsed_time
                    print(f"帧率: {frame_rate:.2f} FPS")
                    # 重置计数和时间
                    frame_count = 0
                    start_time = time.time()
                return matrix
            else:
                return None
        else:
            continue


def update_frame(frame, img):
    # 从串口读取数据
    matrix = read_data()
    if matrix is not None:
        img.set_data(matrix)
    return [img]


def main():
    fig, ax = plt.subplots()
    initial_matrix = np.zeros((num_rows, num_cols))
    img = ax.imshow(initial_matrix, cmap='hot', interpolation='nearest', vmin=0, vmax=1023)
    fig.colorbar(img, ax=ax)

    # 设置动画
    ani = animation.FuncAnimation(fig, update_frame, fargs=(img,), interval=20, blit=True, cache_frame_data=False)
    plt.show()


if __name__ == '__main__':
    main()

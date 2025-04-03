# 说明：
# 传回的数据格式为：传感器的编号 合力值 FX FY FZ  第 1 个传感器测点的力值 FX FY FZ  第 2 个传感器测点的力值 FX FY FZ  。。。。
# 其中，传感器的编号为 12 表示大拇指，5 表示食指。
# 合力值：由三个测点的合力值组成，即 FX+FY+FZ。
# FX FY FZ：分别表示 X 轴、Y 轴、Z 轴方向的力值。
# 传回的手掌的数据，只有前25个是有用的，因为只有25个点，我的这个是支持36个点的，所以传回来的有36个数据
import serial
import time

# 配置串口
serial_port = 'COM22'  # 根据您的实际端口修改
baud_rate = 2000000  # 设置波特率


def main():
    line_count = 0  # 用于统计接收到的行数
    frame_rate_interval = 1.0  # 每秒统计一次帧率
    start_time = time.time()  # 记录开始时间

    # 打开串口
    with serial.Serial(serial_port, baud_rate, timeout=1) as ser:

        while True:
            line = ser.readline()  # 读取一行数据
            if line:
                try:
                    data = line.decode('latin-1').strip()
                    values = list(map(int, data.split(' ')))
                    # 处理数据
                    if values[0] == 1:
                        print("手掌:", values[1:])  # 输出数据（除开开头的1)
                    elif values[0] == 12:
                        print("拇指:", values[1:])  # 输出数据（除开开头的12)
                    elif values[0] == 5:
                        print("食指:", values[1:])  # 输出数据（除开开头的5）
                    line_count += 1  # 每接收到一行数据增加计数
                    # 计算并打印帧率
                    current_time = time.time()
                    if current_time - start_time >= frame_rate_interval:
                        frame_rate = line_count / (current_time - start_time)
                        print(f"帧率: {frame_rate:.2f} FPS")  # 打印帧率
                        line_count = 0  # 重置计数
                        start_time = current_time  # 更新开始时间
                except ValueError as ve:
                    print(f"ValueError: {ve}")  # 输入格式不正确
                except UnicodeDecodeError as ude:
                    print(f"UnicodeDecodeError: {ude}")  # 解码错误
                except Exception as e:
                    print(f"An error occurred: {e}")
            else:
                print("No data received.")


if __name__ == "__main__":
    main()

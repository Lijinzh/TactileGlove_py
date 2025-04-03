import serial
import struct
import glove_data_pb2
import time
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import threading

# 设置字体为常用字体
import matplotlib

matplotlib.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Liberation Sans']  # 可以使用常见字体
matplotlib.rcParams['axes.unicode_minus'] = True  # 正常显示负号

# 传感器数据存储
sensor_data_storage = {}


def receive_protobuf_data(serial_port):
    while True:
        while True:
            start_byte = serial_port.read(1)
            if start_byte == b'\xAA':
                break

        length_bytes = serial_port.read(2)
        message_length = struct.unpack('<H', length_bytes)[0]

        message_data = serial_port.read(message_length)

        end_byte = serial_port.read(1)
        if end_byte != b'\x55':
            continue

        try:
            all_sensors_data = glove_data_pb2.AllSensorsData()
            all_sensors_data.ParseFromString(message_data)

            timestamp = time.time()
            for sensor_idx, sensor in enumerate(all_sensors_data.sensors):
                if sensor_idx not in sensor_data_storage:
                    sensor_data_storage[sensor_idx] = []
                sensor_data_storage[sensor_idx].append((timestamp, [point.z for point in sensor.points]))

        except Exception:
            continue


def update_plot(frame):
    ax.cla()
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Sensor Value')
    ax.set_title('Real-time Sensor Data')
    ax.grid(True)

    for sensor_idx, data in sensor_data_storage.items():
        if data:
            timestamps, values = zip(*data)
            ax.plot(timestamps, [v[0] for v in values], marker='o', label=f'Sensor {sensor_idx + 1}')

    ax.legend()


def main():
    global ax
    fig, ax = plt.subplots(figsize=(10, 6))

    serial_thread = threading.Thread(target=run_serial)
    serial_thread.daemon = True
    serial_thread.start()

    ani = animation.FuncAnimation(fig, update_plot, interval=100)
    plt.show()


def run_serial():
    try:
        with serial.Serial('/dev/ttyACM1', 6000000, timeout=2) as ser:
            receive_protobuf_data(ser)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        plt.close()

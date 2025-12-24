import socket
import struct
import time

# --- 配置 ---
TCP_IP = "0.0.0.0"  # 监听所有网络接口
TCP_PORT = 8888
BUFFER_SIZE = 1024  # 接收缓冲区大小

# 数据包格式: 头(B)+长度(H)+数据(24f)+尾(B) = 100字节
EXPECTED_PACKET_SIZE = 100
STRUCT_FORMAT = '<BH24fB'

# =================================================================
# [核心修改] 配置您要监控的单个传感器的索引 (范围 0 到 23)
# 例如，0 代表第一个传感器，23 代表最后一个。
# 当您拉伸这个传感器时，“True Update”计数才会增加。
SENSOR_TO_MONITOR_INDEX = 1


# =================================================================


def recv_all(sock, n):
    """一个辅助函数，确保从TCP流中准确接收n个字节的数据"""
    data = bytearray()
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data.extend(packet)
    return data


# --- 主程序 ---
def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((TCP_IP, TCP_PORT))
    server_socket.listen(1)

    print(f"TCP server started. Listening on {TCP_IP}:{TCP_PORT}")
    print(f"--- Monitoring changes on SENSOR INDEX: {SENSOR_TO_MONITOR_INDEX} ---")

    while True:
        print("\nWaiting for an ESP32 client to connect...")
        conn, addr = server_socket.accept()
        print(f"Connection accepted from: {addr}")

        # --- 初始化统计变量 ---
        last_print_time = time.time()
        packets_in_second = 0
        updates_in_second = 0

        last_resistor_value = None  # [修改] 从存储整个数组变为只存储一个值

        try:
            while True:
                data = recv_all(conn, EXPECTED_PACKET_SIZE)
                if data is None:
                    print("Client disconnected.")
                    break

                packets_in_second += 1

                unpacked_data = struct.unpack(STRUCT_FORMAT, data)
                header, data_len, footer = unpacked_data[0], unpacked_data[1], unpacked_data[-1]

                if header != 0xAA or footer != 0x55 or data_len != 96:
                    print(f"Warning: Received corrupted packet.")
                    continue

                # 3. [核心逻辑修改] 只提取并对比指定传感器的值
                all_resistors = unpacked_data[2:-1]
                current_resistor_value = all_resistors[SENSOR_TO_MONITOR_INDEX]

                # 如果这是第一个包，或者当前值与上一个值不同
                if last_resistor_value is None or current_resistor_value != last_resistor_value:
                    updates_in_second += 1  # 真实更新计数器+1

                # 更新"上一个值"
                last_resistor_value = current_resistor_value

                # 4. 每秒钟打印一次统计结果
                current_time = time.time()
                if current_time - last_print_time >= 1.0:
                    transmission_fps = packets_in_second / (current_time - last_print_time)
                    update_hz = updates_in_second / (current_time - last_print_time)

                    print(
                        f"Transmission: {transmission_fps:.1f} FPS | True Update: {update_hz:.1f} Hz | Monitored Value: {current_resistor_value:.2f}")

                    packets_in_second = 0
                    updates_in_second = 0
                    last_print_time = current_time

        except ConnectionResetError:
            print("Client connection was forcibly closed.")
        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            conn.close()


if __name__ == '__main__':
    main()

import socket
import struct
import time

# --- 配置 ---
UDP_IP = "0.0.0.0"
UDP_PORT = 8888

# [修复] C++发送的包是 1(头) + 2(长度) + 96(数据) + 1(尾) = 100字节
EXPECTED_PACKET_SIZE = 100
# [修复] struct.unpack格式: 1个无符号字符(B), 1个无符号短整型(H), 24个float(f), 1个无符号字符(B)
STRUCT_FORMAT = '<BH24fB'

# --- 主程序 ---
def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))
    print(f"UDP receiver started. Listening on {UDP_IP}:{UDP_PORT}")
    print("Waiting for ADC data...")
    print("-" * 30)

    last_print_time = time.time()
    packets_in_second = 0

    while True:
        try:
            data, addr = sock.recvfrom(1024)

            if len(data) != EXPECTED_PACKET_SIZE:
                print(f"Warning: Received packet with wrong size. Got {len(data)}, expected {EXPECTED_PACKET_SIZE}.")
                continue

            unpacked_data = struct.unpack(STRUCT_FORMAT, data)

            # [新增] 从解包后的元组中提取数据
            header = unpacked_data[0]
            data_len = unpacked_data[1]
            resistors = unpacked_data[2:-1] # 提取中间的24个浮点数
            footer = unpacked_data[-1]

            # [新增] 校验帧头、帧尾和数据长度
            if header != 0xAA or footer != 0x55 or data_len != 96:
                print(f"Warning: Received corrupted packet. Header: {header}, Footer: {footer}, Len: {data_len}")
                continue

            packets_in_second += 1

            current_time = time.time()
            if current_time - last_print_time >= 1.0:
                fps = packets_in_second / (current_time - last_print_time)
                is_data_zero = all(v == 0.0 for v in resistors)
                print(f"FPS: {fps:.1f} | Data is all zero: {is_data_zero}")
                print(f"  Resistors: [{resistors[0]:.2f}, {resistors[1]:.2f}, {resistors[2]:.2f}, ...]")
                print("-" * 30)

                packets_in_second = 0
                last_print_time = current_time

        except struct.error as e:
            print(f"Struct unpacking error: {e}. Check if packet format is correct.")
        except Exception as e:
            print(f"An error occurred: {e}")

if __name__ == '__main__':
    main()


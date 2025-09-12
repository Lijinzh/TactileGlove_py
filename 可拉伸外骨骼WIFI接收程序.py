import socket
import struct
import numpy as np
import time
from collections import deque

ROWS = 6   # 数组行数
COLS = 4   # 数组列数

class HighSpeedReceiver:
    def __init__(self):
        self.buffer = bytearray()
        self.fps_tracker = deque(maxlen=30)
        self.latest_reversed_data = []  # 存储最新一帧反转后的扁平化数据

    def receive(self, sock):
        try:
            data = sock.recv(4096)
            if not data:
                return None
            self.buffer.extend(data)

            frame = None
            while True:
                extracted_frame = self._extract_frame()
                if extracted_frame is None:
                    break
                frame = extracted_frame  # 只保留最后一帧
                self.fps_tracker.append(time.time())

            if frame is not None:
                # 将每行反转后，直接展平成一个列表
                self.latest_reversed_data = []
                for row in frame:
                    self.latest_reversed_data.extend(row[::-1].tolist())  # 反转行并直接扩展到大列表

            return frame
        except Exception as e:
            print(f"Receive error: {e}")
            return None

    def _extract_frame(self):
        start = self.buffer.find(b'\xAA')
        if start == -1:
            return None

        if len(self.buffer) < start + 3:
            return None

        data_len = struct.unpack('<H', self.buffer[start+1:start+3])[0]
        total_len = 3 + data_len + 1

        if len(self.buffer) < start + total_len:
            return None

        if self.buffer[start + total_len - 1] != 0x55:
            print("Frame tail error!")
            del self.buffer[:start + total_len]
            return None

        data = self.buffer[start+3:start+3+data_len]
        del self.buffer[:start + total_len]

        return np.frombuffer(data, dtype=np.float32).reshape((ROWS, COLS))

    def get_fps(self):
        if len(self.fps_tracker) < 2:
            return 0
        return (len(self.fps_tracker) - 1) / (self.fps_tracker[-1] - self.fps_tracker[0])

if __name__ == "__main__":
    HOST, PORT = '0.0.0.0', 8888
    receiver = HighSpeedReceiver()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.bind((HOST, PORT))
        s.listen()
        print(f"Listening on {HOST}:{PORT}...")
        conn, addr = s.accept()
        print(f"Connected by {addr}")

        try:
            while True:
                frame = receiver.receive(conn)
                if frame is not None:
                    fps = receiver.get_fps()
                    print(f"\rFPS: {fps:.1f} | Latest data: {receiver.latest_reversed_data}", end="")
        except KeyboardInterrupt:
            print("\nStopped.")

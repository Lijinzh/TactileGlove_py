# imu_robot_controller.py
# Description:
# The backend controller for the FR3 robot. It reads IMU data,
# listens to commands from the GUI via the shared state, and sends
# velocity commands to the robot. This script has no GUI components.

import sys
import serial
import struct
import time
import numpy as np
from threading import Thread

from scipy.spatial.transform import Rotation
from franky import Robot, CartesianVelocityMotion, Twist, Duration

# --- Import the shared state object ---
from shared_state import shared_state

# --- Configuration and Constants ---
SERIAL_PORT = 'COM10'
BAUD_RATE = 6000000
ROBOT_IP = '172.16.0.2'
CONTROL_FREQUENCY = 100
P_GAIN = 0.9
PACKET_FORMAT = '<BB13fB'
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)
PACKET_HEADER = (0xAA, 0xBB)

class SerialDataReader:
    """Reads and parses data from the IMU sensor in a separate thread."""
    def __init__(self, port, baudrate):
        self.ser = None
        try:
            self.ser = serial.Serial(port, baudrate, timeout=0.1)
            print(f"Controller: Successfully opened serial port {port}")
        except serial.SerialException as e:
            print(f"Controller ERROR: Could not open serial port {port}. {e}")
        self.buffer = bytearray()
        self.latest_data_packet = None
        self.lock = shared_state.lock
        self.thread = None

    def _calculate_checksum(self, data_bytes: bytes) -> int:
        checksum = 0
        for byte in data_bytes: checksum ^= byte
        return checksum

    def _read_loop(self):
        while shared_state.is_running and self.ser:
            try:
                self.buffer.extend(self.ser.read(self.ser.in_waiting or 1))
                while len(self.buffer) >= PACKET_SIZE:
                    header_index = self.buffer.find(bytes(PACKET_HEADER))
                    if header_index == -1:
                        self.buffer = self.buffer[-(PACKET_SIZE - 1):]
                        break
                    if header_index > 0: self.buffer = self.buffer[header_index:]
                    if len(self.buffer) < PACKET_SIZE: break
                    packet_bytes = self.buffer[:PACKET_SIZE]
                    self.buffer = self.buffer[PACKET_SIZE:]
                    try:
                        *_, received_checksum = struct.unpack(PACKET_FORMAT, packet_bytes)
                        data_bytes_for_checksum = packet_bytes[2:-1]
                        if self._calculate_checksum(data_bytes_for_checksum) == received_checksum:
                            with self.lock:
                                self.latest_data_packet = np.array(struct.unpack('<13f', data_bytes_for_checksum))
                    except struct.error: pass
            except serial.SerialException:
                print("Controller: Serial read error. Thread stopping.")
                break
            time.sleep(0.001)

    def start(self):
        if self.thread is None and self.ser:
            self.thread = Thread(target=self._read_loop, daemon=True)
            self.thread.start()

    def get_latest_data(self) -> np.ndarray | None:
        with self.lock:
            data = self.latest_data_packet
            self.latest_data_packet = None
            return data

    def close(self):
        if self.ser and self.ser.is_open: self.ser.close()


def control_loop(reader: SerialDataReader):
    """The main robot control loop."""
    robot = None
    try:
        robot = Robot(ROBOT_IP)
        robot.recover_from_errors()
        robot.relative_dynamics_factor = 0.2
        print("Controller: FR3 Robot connected successfully.")
        with shared_state.lock:
            shared_state.robot_connected = True
    except Exception as e:
        print(f"Controller ERROR: Could not connect to FR3 Robot: {e}")
        with shared_state.lock:
            shared_state.robot_connected = False

    initial_imu_rotation = None
    last_sent_command = np.zeros(6)

    while shared_state.is_running:
        loop_start_time = time.time()

        data_packet = reader.get_latest_data()
        if data_packet is None:
            time.sleep(0.005)
            continue

        euler_angles_deg = data_packet[0:3]
        current_imu_rotation = Rotation.from_euler('xyz', euler_angles_deg, degrees=True)

        with shared_state.lock:
            shared_state.latest_imu_euler = euler_angles_deg

        if shared_state.reset_zero_pose_requested:
            initial_imu_rotation = current_imu_rotation
            with shared_state.lock:
                shared_state.reset_zero_pose_requested = False
            print("Controller: IMU zero pose has been reset.")

        tool_velocity_command = np.zeros(6)
        if shared_state.control_active and shared_state.robot_connected and initial_imu_rotation is not None:
            relative_imu_rotation = current_imu_rotation * initial_imu_rotation.inv()
            current_pose_matrix = robot.current_pose.matrix
            current_robot_rotation = Rotation.from_matrix(current_pose_matrix[:3, :3])
            error_rotation = relative_imu_rotation * current_robot_rotation.inv()
            angular_velocity_command = P_GAIN * error_rotation.as_rotvec()
            tool_velocity_command[3:] = angular_velocity_command

        with shared_state.lock:
            shared_state.latest_velocity_command = tool_velocity_command
            shared_state.controller_status = "ACTIVE" if shared_state.control_active else "IDLE"

        if shared_state.robot_connected and (shared_state.control_active or np.any(last_sent_command != 0)):
            twist = Twist(linear_velocity=tool_velocity_command[:3], angular_velocity=tool_velocity_command[3:])
            motion = CartesianVelocityMotion(twist, duration=Duration(50))
            robot.move(motion, asynchronous=True)
            last_sent_command = tool_velocity_command

        elapsed = time.time() - loop_start_time
        sleep_time = (1.0 / CONTROL_FREQUENCY) - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    if shared_state.robot_connected:
        print("Controller: Stopping robot...")
        robot.move(CartesianVelocityMotion(Twist([0,0,0],[0,0,0]), duration=Duration(100)))
        robot.join_motion()
    print("Controller: Control loop finished.")


if __name__ == '__main__':
    print("--- Starting FR3 IMU Robot Controller (Backend) ---")
    reader = SerialDataReader(SERIAL_PORT, BAUD_RATE)
    if not reader.ser:
        print("--- Controller exiting due to serial port error. ---")
        sys.exit(1)

    reader.start()

    try:
        control_loop(reader)
    except KeyboardInterrupt:
        print("Controller: Keyboard interrupt detected. Shutting down.")
    finally:
        with shared_state.lock:
            shared_state.is_running = False
        reader.close()
        print("--- FR3 IMU Robot Controller has shut down. ---")

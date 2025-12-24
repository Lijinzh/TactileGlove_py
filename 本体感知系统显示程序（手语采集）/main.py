import perception_data_processor
import data_display_gui
import config_utils
import socket  # 用于网络通信
# 导入PyQt5相关组件用于GUI界面
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
                             QLabel, QVBoxLayout, QFrame, QPushButton)
import threading
import queue
import mono_open3d_vis
import numpy as np

# 导入异步I/O库，用于处理异步操作
import asyncio
# 导入系统特定的参数和函数
import sys
# 导入时间访问和转换模块
import time
# 从自定义模块revo2_utils中导入硬件通信库libstark和日志记录器logger
from revo2_utils import libstark, logger


class DexterousHandController:
    """灵巧手控制器类"""

    def __init__(self, port="COM5", slave_id=0x7f):
        """
        初始化灵巧手控制器

        :param port: 串口端口名称
        :param slave_id: 从设备ID
        """
        self.port = port
        self.slave_id = slave_id
        self.baudrate = libstark.Baudrate.Baud460800
        self.client = None
        self.is_connected = False
        self.speeds = [1000] * 6  # 默认速度

    def connect(self):
        """连接灵巧手设备"""
        try:
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # 运行连接协程
            result = loop.run_until_complete(self._connect_async())
            loop.close()
            return result
        except Exception as e:
            logger.critical(f"Connection failed: {e}")
            return False

    async def _connect_async(self):
        """异步连接方法"""
        # 异步打开Modbus串口连接
        self.client = await libstark.modbus_open(self.port, self.baudrate)
        # 检查串口连接是否成功
        if not self.client:
            logger.critical(f"Failed to open serial port: {self.port}")
            return False
        # 异步获取指定从设备的信息
        info = await self.client.get_device_info(self.slave_id)
        # 检查设备信息获取是否成功
        if not info:
            logger.critical(f"Failed to get device info for right hand. Id: {self.slave_id}")
            return False
        # 记录设备描述信息到日志
        logger.info(f"Right: {info.description}")
        # 设置手指单元模式为归一化模式
        await self.client.set_finger_unit_mode(self.slave_id, libstark.FingerUnitMode.Normalized)

        self.is_connected = True
        return True

    def disconnect(self):
        """断开灵巧手设备连接"""
        if self.is_connected and self.client:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._disconnect_async())
                loop.close()
            except Exception as e:
                logger.error(f"Disconnection error: {e}")
            finally:
                self.is_connected = False

    async def _disconnect_async(self):
        """异步断开连接方法"""
        # 异步关闭Modbus串口连接
        await libstark.modbus_close(self.client)
        logger.info("Hand disconnected")

    def set_positions(self, positions):
        """
        设置手指位置

        :param positions: 包含6个手指位置的列表
        """
        if not self.is_connected:
            logger.warning("Hand is not connected")
            return False

        if len(positions) != 6:
            logger.error("Positions list must contain exactly 6 values")
            return False

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self._set_positions_async(positions))
            loop.close()
            return result
        except Exception as e:
            logger.error(f"Error setting positions: {e}")
            return False

    async def _set_positions_async(self, positions):
        """异步设置位置方法"""
        # 异步设置手指位置和速度
        await self.client.set_finger_positions_and_speeds(self.slave_id, positions, self.speeds)
        logger.info(f"Set positions: {positions}")
        return True

    def move_to_default(self):
        """移动到默认位置"""
        return self.set_positions([0, 0, 0, 0, 0, 0])

    def move_finger(self, finger_index, position):
        """
        控制单个手指

        :param finger_index: 手指索引 (0-5)
        :param position: 位置值
        """
        if not 0 <= finger_index <= 5:
            logger.error("Finger index must be between 0 and 5")
            return False

        positions = [0, 0, 0, 0, 0, 0]
        positions[finger_index] = position
        return self.set_positions(positions)


class HandControlThread(threading.Thread):
    """独立的灵巧手高速控制线程"""

    def __init__(self, hand_controller, control_rate=1000):
        """
        初始化控制线程

        :param hand_controller: 灵巧手控制器实例
        :param control_rate: 控制频率 (Hz)
        """
        super().__init__()
        self.hand_controller = hand_controller
        self.control_rate = control_rate
        self.target_positions = [0] * 6
        self.current_positions = [0] * 6
        self.running = False
        self.lock = threading.Lock()
        self.filter_factor = 0.25  # 平滑因子

    def set_target_positions(self, positions):
        """设置目标位置"""
        with self.lock:
            self.target_positions = positions[:]

    def get_current_positions(self):
        """获取当前位置"""
        with self.lock:
            return self.current_positions[:]

    def run(self):
        """线程主循环"""
        self.running = True
        interval = 1.0 / self.control_rate

        while self.running:
            start_time = time.time()

            # 更新位置并控制灵巧手
            with self.lock:
                for i in range(6):
                    # 平滑逼近目标位置
                    diff = self.target_positions[i] - self.current_positions[i]
                    self.current_positions[i] += diff * self.filter_factor
                    # 限制范围
                    self.current_positions[i] = max(0, min(1000, self.current_positions[i]))

            # 控制灵巧手
            try:
                self.hand_controller.set_positions([int(pos) for pos in self.current_positions])
            except Exception as e:
                print(f"灵巧手控制错误: {e}")

            # 精确时间控制
            elapsed = time.time() - start_time
            sleep_time = max(0, interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def stop(self):
        """停止线程"""
        self.running = False
        self.join()


class VisualizerThread(threading.Thread):
    """可视化器线程类，用于在独立线程中运行手部可视化"""

    def __init__(self, is_rhand=True):
        super().__init__()
        self.is_rhand = is_rhand
        self.data_queue = queue.Queue(maxsize=10)  # 限制队列大小，避免内存溢出
        self.visualizer = None
        self.running = False
        self.daemon = True  # 设置为守护线程，主线程结束时自动退出

    def run(self):
        """线程主函数"""
        try:
            # 创建右手可视化器实例
            self.visualizer = mono_open3d_vis.MANOHandVisualizer(is_rhand=self.is_rhand)
            self.running = True

            print("可视化器线程已启动")

            # 主循环 - 处理数据更新和可视化
            while self.running:
                try:
                    # 从队列中获取数据，设置超时以允许检查running状态
                    glove_data = self.data_queue.get(timeout=0.01)

                    # 更新手部姿态
                    self.visualizer.update_hand_pose(glove_data)

                    # 更新渲染
                    if self.visualizer.vis.poll_events():
                        self.visualizer.vis.update_renderer()
                    else:
                        # 用户关闭了可视化窗口，停止线程
                        self.running = False

                except queue.Empty:
                    # 队列为空，继续检查事件
                    if self.visualizer and self.visualizer.vis.poll_events():
                        self.visualizer.vis.update_renderer()
                    continue
                except Exception as e:
                    print(f"可视化器线程处理数据时出错: {e}")
                    continue

        except Exception as e:
            print(f"可视化器线程启动失败: {e}")
        finally:
            # 清理资源
            if self.visualizer:
                self.visualizer.vis.destroy_window()
            print("可视化器线程已结束")

    def update_data(self, glove_data_24d):
        """向可视化器线程发送新的手套数据"""
        if not self.running:
            return

        try:
            # 将数据放入队列，如果队列满则移除旧数据
            if self.data_queue.full():
                try:
                    self.data_queue.get_nowait()
                except queue.Empty:
                    pass
            self.data_queue.put_nowait(np.array(glove_data_24d))
        except Exception as e:
            print(f"向可视化器线程发送数据时出错: {e}")

    def stop(self):
        """停止可视化器线程"""
        self.running = False


# 定义24元素的调整参数
# 缩放系数：负数表示取反，绝对值表示缩放比例
scale_factors = np.array([
    2.0,  # 第0维：保持符号，1.0倍缩放
    2.0,  # 第1维：保持符号，1.0倍缩放
    5.5,  # 第2维：取反，1.5倍缩放
    5.5,  # 第3维：取反，2.0倍缩放
    4,  # 第4维：取反，1.2倍缩放
    1.0,  # 第5维：保持符号，1.0倍缩放
    1.0,  # 第6维：保持符号，1.0倍缩放
    4.5,  # 第7维：保持符号，1.0倍缩放
    2.5,  # 第8维：保持符号，1.0倍缩放
    -4.5,  # 第9维：保持符号，1.0倍缩放
    1.0,  # 第10维：保持符号，1.0倍缩放
    1.0,  # 第11维：保持符号，1.0倍缩放
    1.0,  # 第12维：保持符号，1.0倍缩放
    -2.0,  # 第13维：保持符号，1.0倍缩放
    5.5,  # 第14维：保持符号，1.0倍缩放
    5.5,  # 第15维：保持符号，1.0倍缩放
    1.0,  # 第16维：保持符号，1.0倍缩放
    1,  # 第17维：取反，1.8倍缩放
    4.5,  # 第18维：保持符号，1.0倍缩放
    5.5,  # 第19维：保持符号，1.0倍缩放
    1.0,  # 第20维：保持符号，1.0倍缩放
    1.0,  # 第21维：保持符号，1.0倍缩放
    1.0,  # 第22维：保持符号，1.0倍缩放
    1.0,  # 第23维：保持符号，1.0倍缩放
])
# 定义24元素的偏移量数组
offsets = np.array([
    -0.2,  # 第0维：偏移量0
    0.1,  # 第1维：偏移量0
    -0.5,  # 第2维：偏移量0.1
    -0.5,  # 第3维：偏移量-0.05
    -0.5,  # 第4维：偏移量0
    -0.4,  # 第5维：偏移量0
    -0.2,  # 第6维：偏移量0
    -0.5,  # 第7维：偏移量0
    0.5,  # 第8维：偏移量0
    0.5,  # 第9维：偏移量0
    0.0,  # 第10维：偏移量0
    0.0,  # 第11维：偏移量0
    0.0,  # 第12维：偏移量0
    0.0,  # 第13维：偏移量0
    -0.6,  # 第14维：偏移量0
    -0.5,  # 第15维：偏移量0
    0,  # 第16维：偏移量0
    0,  # 第17维：偏移量0
    -0.6,  # 第18维：偏移量0
    -0.6,  # 第19维：偏移量0
    0.0,  # 第20维：偏移量0
    0.0,  # 第21维：偏移量0
    0.0,  # 第22维：偏移量0
    0.0,  # 第23维：偏移量0
])

# 程序入口点
if __name__ == "__main__":
    HOST, PORT = '0.0.0.0', 8888  # 定义服务器地址和端口
    receiver = data_display_gui.HighSpeedReceiver()  # 创建接收器实例

    # 创建socket连接
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # 创建TCP socket
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # 禁用Nagle算法提高实时性
    s.bind((HOST, PORT))  # 绑定地址和端口
    s.listen()  # 开始监听连接
    print(f"Listening on {HOST}:{PORT}...")  # 打印监听信息
    conn, addr = s.accept()  # 接受客户端连接
    print(f"Connected by {addr}")  # 打印连接信息

    # 创建并启动可视化器线程
    visualizer_thread = VisualizerThread(is_rhand=True)
    visualizer_thread.start()

    # 启动Qt应用
    app = QApplication([])  # 创建Qt应用程序
    display = data_display_gui.DataDisplay(receiver, conn)  # 创建显示窗口，传入conn对象
    display.show()  # 显示窗口

    # 灵巧手控制初始化 - 使用新的简单类
    hand_controller = DexterousHandController(port="COM5")
    hand_connected = hand_controller.connect()
    hand_control_thread = None
    if hand_connected:
        print("灵巧手连接成功")
        # 初始化到默认位置
        hand_controller.move_to_default()
        # 启动独立的控制线程
        hand_control_thread = HandControlThread(hand_controller, control_rate=100)  # 100Hz高速控制
        hand_control_thread.start()
    else:
        print("灵巧手连接失败")

    try:
        # 主循环 - 处理数据接收和转发到可视化器
        while True:
            # 处理Qt事件
            app.processEvents()  # 如果想让QT实时显示，就取消注释这一行，但是会比较卡顿
            # 接收数据
            frame = receiver.receive(conn)
            if frame is not None:
                # 是用这个Receiver直接获取到数据，绕过UI界面，UI界面太慢了
                resistances, glove_data_24d = display.exoskeleton.calculate_real_time_stretch(
                    receiver.latest_reversed_data)
                # 将24维数据发送到可视化器线程
                # glove_data_24d = display.my_stretch_ratios[:24]  # 确保是24维
                if len(glove_data_24d) == 24:
                    adjusted_data = np.array(glove_data_24d)
                    if hand_connected and hand_control_thread:
                        try:
                            # 使用指定位置的元素：7, 3, 18, 19 以及另外两个位置
                            # 这里我假设您需要6个位置，所以添加了位置0和1作为示例
                            # 您可以根据实际需要调整这些索引
                            finger_indices = [8, 5, 4, 2, 14, 15]  # 6个手指对应的数据索引

                            hand_positions = []
                            for i in range(6):  # 6个手指
                                # 获取指定位置的数据
                                finger_value = adjusted_data[finger_indices[i]]
                                if i == 0:
                                    finger_value = adjusted_data[finger_indices[i]] + adjusted_data[9]
                                # 映射到0-1000范围
                                position = int(finger_value * 3000)  # 根据需要调整映射关系
                                position = max(0, min(1000, position))  # 限制在有效范围内
                                hand_positions.append(position)

                            # 控制灵巧手
                            # 发送目标位置到控制线程
                            hand_control_thread.set_target_positions(hand_positions)
                            # hand_controller.set_positions(hand_positions)
                            # 可选：打印当前控制数据用于调试
                            # print(f"Hand positions: {hand_positions}")

                        except Exception as e:
                            print(f"灵巧手控制错误: {e}")

                    # 应用缩放和偏移：先缩放，再加偏移
                    adjusted_data = adjusted_data * scale_factors + offsets
                    # print(glove_data_24d)
                    visualizer_thread.update_data(adjusted_data.tolist())

    except KeyboardInterrupt:  # 捕获键盘中断
        print("\nStopped.")  # 打印停止信息
    finally:
        # 停止所有线程
        if hand_control_thread:
            hand_control_thread.stop()
        visualizer_thread.stop()
        if hand_connected:
            hand_controller.disconnect()
            print("灵巧手已断开")
        # 停止可视化器线程
        visualizer_thread.stop()
        conn.close()  # 关闭客户端连接
        s.close()  # 关闭服务器socket

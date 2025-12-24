import socket
import struct
import numpy as np
import time
import csv
import os
import sys
from collections import deque
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
                             QLabel, QVBoxLayout, QFrame, QPushButton, QProgressBar,
                             QSpacerItem, QSizePolicy, QGridLayout, QMessageBox,
                             QLineEdit, QComboBox, QSplitter)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QRect
from PyQt5.QtGui import QColor, QPixmap, QFont, QPainter, QPen, QBrush

# --- 1. 基础配置区域 (网络与参数) ---
HOST, PORT = '0.0.0.0', 8888  # 监听地址和端口
ROWS = 6  # 传感器行数
COLS = 4  # 传感器列数
TOTAL_CELLS = ROWS * COLS  # 总传感器数量
REFERENCE_VOLTAGE = 3300.0    # 参考电压 (mV)
REFERENCE_RESISTANCE = 3000.0 # 参考电阻 (Ohm)

CAPTURE_DURATION = 2.0        # 每个动作采集时长 (秒)
PRE_CAPTURE_DURATION = 0.5    # 采集前预留时长 (秒)
TOTAL_REPS_PER_GESTURE = 1    # 每个手势重复次数
CALIBRATION_INTERVAL = 5      # 校准间隔 (每几次动作校准一次)

# 【统一字体配置】
# 将此处修改为您想要的字体，即可全局生效
UI_FONT_FAMILY = "Microsoft YaHei"

# --- 2. 颜色配置 (苹果风格) ---
COLOR_BG_GRAY = "#F5F5F7"         # 背景灰
COLOR_CARD_WHITE = "#FFFFFF"      # 卡片白
COLOR_TEXT_PRIMARY = "#1D1D1F"    # 主要文字色
COLOR_TEXT_SECONDARY = "#86868B"  # 次要文字色
COLOR_APPLE_BLUE = "#007AFF"      # 苹果蓝
COLOR_APPLE_GREEN = "#34C759"     # 苹果绿
COLOR_APPLE_RED = "#FF3B30"       # 苹果红
COLOR_APPLE_ORANGE = "#FF9500"    # 苹果橙
COLOR_BORDER = "#D2D2D7"          # 边框色

# --- 3. 手势列表内容 ---
GESTURE_LIST = [
    "Wrist abduction", "Wrist adduction", "Wrist flexion", "Wrist extension",
    "Fist (thumbs in)", "Open paper", "Close paper",
    "Thumbs and index", "Thumbs and middle", "Thumbs and ring", "Thumbs and pinky",
    "Middle and ring",
    "Letter A", "Letter B", "Letter C", "Letter D", "Letter E",
    "Letter F", "Letter G", "Letter H", "Letter I", "Letter J",
    "Letter K", "Letter L", "Letter M", "Letter N", "Letter O",
    "Letter P", "Letter Q", "Letter R", "Letter S", "Letter T",
    "Letter U", "Letter V", "Letter W", "Letter X", "Letter Y",
    "Letter Z",
    "Number 0", "Number 1", "Number 2", "Number 3", "Number 4",
    "Number 5", "Number 6", "Number 7", "Number 8", "Number 9"
]

# --- 4. 业务逻辑类 (无需修改外观) ---
class StretchableExoskeleton:
    def __init__(self):
        self.voltage_ref = REFERENCE_VOLTAGE
        self.r_ref = REFERENCE_RESISTANCE

    # 电压转电阻算法
    def voltage_to_resistance(self, voltage):
        if voltage <= 0 or voltage >= self.voltage_ref: return 0
        return self.r_ref * (self.voltage_ref - voltage) / voltage

class HighSpeedReceiver:
    def __init__(self):
        self.buffer = bytearray()
        self.latest_reversed_data = [0] * TOTAL_CELLS
        self.frame_count = 0
        self.last_fps_calc_time = time.time()
        self.stable_fps = 0.0

    # 接收并解析数据
    def receive(self, sock):
        try:
            data = sock.recv(4096)
            if not data: return None
            self.buffer.extend(data)
            frame = None
            received = False
            while True:
                extracted = self._extract_frame()
                if extracted is None: break
                frame = extracted
                self.frame_count += 1
                received = True
            if frame is not None:
                flat_data = []
                for row in frame:
                    # 注意：这里进行了数据翻转处理
                    flat_data.extend(row[::-1].tolist())
                self.latest_reversed_data = flat_data[:TOTAL_CELLS]
            return frame if received else None
        except BlockingIOError: return None
        except Exception as e: return None

    # 从缓冲区提取完整的一帧数据
    def _extract_frame(self):
        start = self.buffer.find(b'\xAA') # 帧头
        if start == -1: return None
        if len(self.buffer) < start + 3: return None
        data_len = struct.unpack('<H', self.buffer[start + 1:start + 3])[0]
        if data_len != TOTAL_CELLS * 4:
            del self.buffer[:start + 1]
            return None
        total_len = 3 + data_len + 1
        if len(self.buffer) < start + total_len: return None
        if self.buffer[start + total_len - 1] != 0x55: # 帧尾
            del self.buffer[:start + 1]
            return None
        data = self.buffer[start + 3:start + 3 + data_len]
        del self.buffer[:start + total_len]
        return np.frombuffer(data, dtype=np.float32).reshape((ROWS, COLS))

    # 计算 FPS
    def get_fps(self):
        cur = time.time()
        if cur - self.last_fps_calc_time >= 1.0:
            self.stable_fps = self.frame_count / (cur - self.last_fps_calc_time)
            self.frame_count = 0
            self.last_fps_calc_time = cur
        return self.stable_fps

class DataWorker(QThread):
    data_received = pyqtSignal(list, float) # 信号：发送数据列表和FPS
    def __init__(self, receiver, conn):
        super().__init__()
        self.receiver = receiver
        self.conn = conn
        self.running = True
    def run(self):
        while self.running and self.conn:
            frame = self.receiver.receive(self.conn)
            if frame is not None:
                fps = self.receiver.get_fps()
                self.data_received.emit(self.receiver.latest_reversed_data, fps)
            else:
                self.msleep(1)
    def stop(self): self.running = False

# --- 5. 自定义控件：右侧手势状态方块 ---
# 【说明】：这个方块是自己画出来的，所以普通的CSS样式表对它里面的文字无效！
# 必须在 paintEvent 函数里修改。
class GestureStatusCell(QFrame):
    clicked = pyqtSignal(int) # 点击信号

    def __init__(self, index, name, parent=None):
        super().__init__(parent)
        self.index = index
        self.name = name
        self.total_reps = TOTAL_REPS_PER_GESTURE
        self.current_reps = 0
        self.is_active = False

        # 【关键修改点 1】：右侧方块的大小
        self.setFixedSize(95, 80)
        self.setFrameStyle(QFrame.NoFrame)
        self.setCursor(Qt.PointingHandCursor)

    def update_status(self, reps, is_active):
        self.current_reps = reps
        self.is_active = is_active
        self.update() # 触发重绘

    # 【关键修改点 2】：右侧方块内部的字体大小与类型
    def paintEvent(self, event):
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            rect = self.rect()

            # 根据状态设置背景色
            if self.current_reps >= self.total_reps:
                bg_color = QColor(COLOR_APPLE_GREEN) # 完成：绿色
                text_color = QColor("white")
            elif self.current_reps > 0:
                bg_color = QColor(COLOR_APPLE_ORANGE) # 进行中：橙色
                text_color = QColor("white")
            else:
                bg_color = QColor("#E5E5EA") # 未开始：灰色
                text_color = QColor(COLOR_TEXT_SECONDARY)

            # 绘制圆角矩形背景
            painter.setPen(Qt.NoPen)
            painter.setBrush(bg_color)
            painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 12, 12)

            # 绘制选中时的蓝色边框
            if self.is_active:
                pen = QPen(QColor(COLOR_APPLE_BLUE))
                pen.setWidth(5) # 边框粗细
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 12, 12)

            # --- 绘制数字文本 ---
            painter.setPen(text_color)

            # 【此处已修改】：统一使用全局字体变量，大小保持您设定的 24
            font = QFont(UI_FONT_FAMILY, 24)
            font.setBold(True)
            painter.setFont(font)

            painter.drawText(rect, Qt.AlignCenter, str(self.index + 1))

            # 绘制进度小圆点
            if self.current_reps > 0 and self.current_reps < self.total_reps:
                painter.setBrush(QColor("white"))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(rect.right()-20, rect.bottom()-20, 10, 10)
        except Exception as e:
            print(f"Paint Error: {e}")

    def mousePressEvent(self, event):
        self.clicked.emit(self.index)

    def enterEvent(self, event):
        # 鼠标悬停显示完整手势名
        self.setToolTip(f"{self.index + 1}. {self.name}\nProgress: {self.current_reps}/{self.total_reps}")
        super().enterEvent(event)

# --- 6. 主窗口类 (核心界面逻辑) ---
class GestureCollectionWindow(QMainWindow):
    def __init__(self, conn):
        super().__init__()
        self.conn = conn
        self.receiver = HighSpeedReceiver()
        self.exo = StretchableExoskeleton()

        # 初始化状态变量
        self.current_gesture_idx = 0
        self.gesture_progress = {i: 0 for i in range(len(GESTURE_LIST))}
        self.current_rep_count = 0
        self.samples_since_calibration = 0
        self.is_collecting = False
        self.needs_calibration = True
        self.start_capture_time = 0
        self.info_locked = False

        # 【关键修改点 3】：中间图片的显示大小
        self.fixed_img_w = 640  # 宽度
        self.fixed_img_h = 900  # 高度

        self.data_buffer = deque(maxlen=200)
        self.current_R0 = None
        self.temp_capture_data = []

        # 数据保存路径
        self.save_dir_base = "collected_data_v2"
        if not os.path.exists(self.save_dir_base):
            os.makedirs(self.save_dir_base)

        self.initUI()

        # 启动数据接收线程
        self.worker = DataWorker(self.receiver, self.conn)
        self.worker.data_received.connect(self.on_data_received)
        self.worker.start()

        self.enter_calibration_state()
        self.update_grid_status()

    def initUI(self):
        self.setWindowTitle('AVATAR Studio (统一字体版)')

        # --- 全局样式表 ---
        # 这里的设置会影响大部分普通的文字、按钮和输入框
        # 【此处已修改】：font-family 统一使用全局变量
        self.setStyleSheet(f"""
            QMainWindow {{ 
                background-color: {COLOR_BG_GRAY}; 
            }}
            
            /* 全局 Label 字体 */
            QLabel {{ 
                color: {COLOR_TEXT_PRIMARY}; 
                font-family: "{UI_FONT_FAMILY}", sans-serif;
                font-size: 48px; /* 基础字体 */
            }}
            
            /* 面板卡片样式 */
            QFrame#panel {{
                background-color: {COLOR_CARD_WHITE};
                border-radius: 16px;
                border: 1px solid #E5E5EA;
            }}
            
            /* 输入框样式 */
            QLineEdit, QComboBox {{ 
                padding: 14px 18px; 
                border: 1px solid {COLOR_BORDER}; 
                border-radius: 12px; 
                background: white; 
                color: {COLOR_TEXT_PRIMARY}; 
                font-family: "{UI_FONT_FAMILY}", sans-serif;
                font-size: 36px;
                selection-background-color: {COLOR_APPLE_BLUE};
            }}
            QLineEdit:focus, QComboBox:focus {{
                border: 2px solid {COLOR_APPLE_BLUE};
            }}
            
            /* 按钮样式 */
            QPushButton {{ 
                background-color: white; 
                color: {COLOR_TEXT_PRIMARY}; 
                padding: 16px 32px; 
                border: 1px solid {COLOR_BORDER};
                border-radius: 12px; 
                font-weight: 600; 
                font-family: "{UI_FONT_FAMILY}", sans-serif;
                font-size: 36px;
            }}
            QPushButton:hover {{ 
                background-color: #F5F5F7; 
            }}
            QPushButton:pressed {{ 
                background-color: #E5E5EA; 
            }}
            
            /* 锁定按钮特殊样式 */
            QPushButton#lockBtn {{ 
                background-color: {COLOR_APPLE_GREEN}; 
                border: 1px solid {COLOR_APPLE_GREEN};
                color: white; 
            }}
            
            /* 进度条样式 (超大号) */
            QProgressBar {{
                border: 1px solid {COLOR_BORDER};
                background-color: #E5E5EA;
                border-radius: 30px; 
                height: 60px; /* 控制进度条高度 */
                text-align: center;
                font-family: "{UI_FONT_FAMILY}", sans-serif;
                font-size: 32px; /* 进度条文字大小 */
                font-weight: bold;
                color: black;
            }}
            QProgressBar::chunk {{
                background-color: {COLOR_APPLE_BLUE};
                border-radius: 29px;
            }}
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(25)

        # === 左侧面板：传感器热力图 ===
        left_panel = QFrame()
        left_panel.setObjectName("panel")
        left_panel.setMinimumWidth(500) # 稍微加宽以适应大字体

        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(20, 25, 20, 25)

        lbl_title = QLabel("Sensors")
        # 【此处已修改】：统一使用全局字体变量
        lbl_title.setFont(QFont(UI_FONT_FAMILY, 48, QFont.Bold))
        left_layout.addWidget(lbl_title)

        left_layout.addSpacing(15)

        grid = QGridLayout()
        grid.setSpacing(12)
        self.sensor_cells = []
        for i in range(TOTAL_CELLS):
            lbl = QLabel("0")
            lbl.setAlignment(Qt.AlignCenter)

            # 【关键修改点 4】左侧传感器格子的初始样式
            # 这里的 font-family 和 font-size 必须和 on_data_received 里的一样！
            lbl.setStyleSheet(f"background-color: #F2F2F7; border-radius: 8px; font-family: \"{UI_FONT_FAMILY}\"; font-size: 36px; font-weight: bold; color: #1D1D1F;")
            lbl.setFixedSize(110, 70)
            grid.addWidget(lbl, i // 4, i % 4)
            self.sensor_cells.append(lbl)
        left_layout.addLayout(grid)

        left_layout.addSpacing(30)
        self.lbl_fps = QLabel("FPS: 0.0")
        self.lbl_fps.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 36px;") # 适配36px
        left_layout.addWidget(self.lbl_fps)

        left_layout.addStretch()

        # 状态指示灯
        self.lbl_status_indicator = QLabel("Wait Calib")
        self.lbl_status_indicator.setAlignment(Qt.AlignCenter)
        self.lbl_status_indicator.setFixedHeight(100) # 加高
        self.lbl_status_indicator.setStyleSheet(f"background-color: {COLOR_APPLE_ORANGE}; color: white; border-radius: 50px; font-family: \"{UI_FONT_FAMILY}\"; font-size: 40px; font-weight: bold;")
        left_layout.addWidget(self.lbl_status_indicator)

        main_layout.addWidget(left_panel)

        # === 中间面板：图片 & 状态 (重构为分散布局) ===
        # 创建一个透明容器来容纳三个部分
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0) # 容器本身无边距
        center_layout.setSpacing(25)

        # 1. 顶部：手势名称 (单独白色卡片，置顶)
        self.frame_top = QFrame()
        self.frame_top.setObjectName("panel") # 使用白色圆角样式
        layout_top = QVBoxLayout(self.frame_top)
        layout_top.setContentsMargins(20, 30, 20, 30)

        self.lbl_gesture_name = QLabel(f"{GESTURE_LIST[0]}")
        self.lbl_gesture_name.setAlignment(Qt.AlignCenter)
        self.lbl_gesture_name.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY};")
        # 【此处已修改】：统一使用全局字体变量
        self.lbl_gesture_name.setFont(QFont(UI_FONT_FAMILY, 80, QFont.Bold)) # 保持特大号
        layout_top.addWidget(self.lbl_gesture_name)

        center_layout.addWidget(self.frame_top)

        # 2. 中间：图片 (独立显示)
        # 使用 addStretch 让图片在垂直方向居中，或者让它靠近顶部/底部
        center_layout.addStretch()

        self.img_display = QLabel()
        self.img_display.setAlignment(Qt.AlignCenter)
        self.img_display.setStyleSheet("background-color: #F2F2F7; border-radius: 12px;")
        self.img_display.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        center_layout.addWidget(self.img_display, 0, Qt.AlignCenter)

        center_layout.addStretch()

        # 3. 底部：提示语和进度条 (单独白色卡片，置底)
        self.frame_bottom = QFrame()
        self.frame_bottom.setObjectName("panel")
        layout_bottom = QVBoxLayout(self.frame_bottom)
        layout_bottom.setContentsMargins(30, 30, 30, 30)
        layout_bottom.setSpacing(20)

        self.lbl_instruction = QLabel("Please Lock Info First")
        self.lbl_instruction.setAlignment(Qt.AlignCenter)
        # 【此处已修改】：统一使用全局字体变量
        self.lbl_instruction.setFont(QFont(UI_FONT_FAMILY, 54, QFont.Bold))
        self.lbl_instruction.setStyleSheet(f"color: {COLOR_APPLE_RED}; margin-bottom: 10px;")
        layout_bottom.addWidget(self.lbl_instruction)

        self.capture_progress = QProgressBar()
        self.capture_progress.setRange(0, 100)
        self.capture_progress.setValue(0)
        layout_bottom.addWidget(self.capture_progress)

        center_layout.addWidget(self.frame_bottom)

        main_layout.addWidget(center_widget)

        # === 右侧面板：用户信息 & 任务网格 ===
        right_panel = QFrame()
        right_panel.setObjectName("panel")
        right_panel.setMinimumWidth(800) # 加宽

        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(30)
        right_layout.setContentsMargins(30, 30, 30, 30)

        # 1. 用户信息标题
        lbl_info_title = QLabel("Subject Info")
        # 【此处已修改】：统一使用全局字体变量
        lbl_info_title.setFont(QFont(UI_FONT_FAMILY, 48, QFont.Bold))
        right_layout.addWidget(lbl_info_title)

        user_group = QWidget()
        user_layout = QGridLayout(user_group)
        user_layout.setSpacing(25)
        user_layout.setContentsMargins(0,0,0,0)

        user_layout.addWidget(QLabel("Name"), 0, 0)
        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("ID")
        user_layout.addWidget(self.input_name, 0, 1)

        user_layout.addWidget(QLabel("Gender"), 0, 2)
        self.combo_gender = QComboBox()
        self.combo_gender.addItems(["M", "F"])
        user_layout.addWidget(self.combo_gender, 0, 3)

        user_layout.addWidget(QLabel("Size"), 1, 0)
        self.combo_size = QComboBox()
        self.combo_size.addItems(["S", "M", "L", "XL"])
        self.combo_size.setCurrentText("M")
        user_layout.addWidget(self.combo_size, 1, 1)

        # 锁定按钮
        self.btn_lock = QPushButton("Lock & Start")
        self.btn_lock.setObjectName("lockBtn")
        self.btn_lock.setCheckable(True)
        self.btn_lock.clicked.connect(self.toggle_lock_info)
        self.btn_lock.setCursor(Qt.PointingHandCursor)
        user_layout.addWidget(self.btn_lock, 1, 2, 1, 2)

        right_layout.addWidget(user_group)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("background-color: #E5E5EA; border: none; max-height: 2px;")
        right_layout.addWidget(line)

        # 2. 任务网格标题
        lbl_grid = QLabel("Tasks")
        # 【此处已修改】：统一使用全局字体变量
        lbl_grid.setFont(QFont(UI_FONT_FAMILY, 48, QFont.Bold))
        right_layout.addWidget(lbl_grid)

        # 任务网格容器
        grid_container = QWidget()
        self.gesture_grid_layout = QGridLayout(grid_container)
        self.gesture_grid_layout.setSpacing(15)
        self.gesture_grid_layout.setContentsMargins(0, 0, 0, 0)

        self.gesture_cells = []
        cols = 6
        for i, g_name in enumerate(GESTURE_LIST):
            cell = GestureStatusCell(i, g_name)
            cell.clicked.connect(self.jump_to_gesture)
            self.gesture_cells.append(cell)
            self.gesture_grid_layout.addWidget(cell, i // cols, i % cols)

        right_layout.addWidget(grid_container)
        right_layout.addStretch()

        # 统计信息
        self.lbl_total_progress = QLabel("0 / 48 Completed")
        self.lbl_total_progress.setAlignment(Qt.AlignRight)
        self.lbl_total_progress.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-weight: 500; font-size: 36px;") # 适配36px
        right_layout.addWidget(self.lbl_total_progress)

        main_layout.addWidget(right_panel)

        self.collection_timer = QTimer()
        self.collection_timer.timeout.connect(self.check_capture_status)

        # 设置图片并调整窗口大小
        self.setup_image_display()
        self.check_lock_status()
        self.adjustSize()

    # --- 功能函数区 ---

    def setup_image_display(self):
        """设置图片显示大小并加载第一张图"""
        self.img_display.setFixedSize(self.fixed_img_w, self.fixed_img_h)
        self.load_gesture_image(0)

    def toggle_lock_info(self):
        """锁定/解锁用户信息"""
        self.info_locked = self.btn_lock.isChecked()

        if self.info_locked:
            if not self.input_name.text().strip():
                QMessageBox.warning(self, "Error", "Please enter a name!")
                self.btn_lock.setChecked(False)
                self.info_locked = False
                return

            self.input_name.setEnabled(False)
            self.combo_gender.setEnabled(False)
            self.combo_size.setEnabled(False)
            self.btn_lock.setText("Unlock")
            self.setFocus()
            self.check_lock_status()
        else:
            self.input_name.setEnabled(True)
            self.combo_gender.setEnabled(True)
            self.combo_size.setEnabled(True)
            self.btn_lock.setText("Lock & Start")
            self.lbl_instruction.setText("Please Lock Info")
            self.lbl_instruction.setStyleSheet(f"color: {COLOR_APPLE_RED}; margin-bottom: 20px;")

    def check_lock_status(self):
        """检查锁定状态并更新UI"""
        if self.info_locked:
            self.enter_calibration_state()
        else:
            self.lbl_instruction.setText("Please Lock Info")
            self.lbl_instruction.setStyleSheet(f"color: {COLOR_APPLE_RED}; margin-bottom: 20px;")
            self.lbl_status_indicator.setText("Info Needed")
            self.lbl_status_indicator.setStyleSheet(f"background-color: #8E8E93; color: white; border-radius: 50px; font-family: \"{UI_FONT_FAMILY}\"; font-weight: bold;")

    def keyPressEvent(self, event):
        """键盘事件处理"""
        if not self.info_locked:
            return
        if event.key() == Qt.Key_C:
            self.perform_calibration()
        elif event.key() == Qt.Key_Space:
            if not self.needs_calibration:
                self.start_capture_gesture()
            else:
                QMessageBox.warning(self, "Tip", "Please press [C] to calibrate first")
        elif event.key() == Qt.Key_Right:
            if not self.is_collecting: self.change_gesture(1)
        elif event.key() == Qt.Key_Left:
            if not self.is_collecting: self.change_gesture(-1)
        elif event.key() == Qt.Key_Escape:
            self.close()

    def change_gesture(self, offset):
        """切换当前手势"""
        new_idx = (self.current_gesture_idx + offset) % len(GESTURE_LIST)
        self.current_gesture_idx = new_idx
        self.current_rep_count = self.gesture_progress[new_idx]
        self.samples_since_calibration = 0
        self.current_R0 = None
        self.update_ui_for_gesture()
        self.enter_calibration_state()

    def load_gesture_image(self, idx):
        """加载对应手势的图片"""
        if idx < 0 or idx >= len(GESTURE_LIST): return
        img_idx = idx + 1
        paths = [
            os.path.join("gesture_images", f"{img_idx}.png"),
            os.path.join("gesture_images", f"{img_idx}.jpg")
        ]
        found = False
        for p in paths:
            if os.path.exists(p):
                pixmap = QPixmap(p)
                self.img_display.setPixmap(pixmap.scaled(
                    self.fixed_img_w, self.fixed_img_h,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation
                ))
                found = True
                break
        if not found:
            self.img_display.setText(f"Missing: {img_idx}")

    def jump_to_gesture(self, idx):
        """点击网格跳转到特定手势"""
        if not self.info_locked:
            QMessageBox.warning(self, "Tip", "Please lock user info first!")
            return
        if self.is_collecting: return
        self.current_gesture_idx = idx
        self.current_rep_count = self.gesture_progress[idx]
        self.samples_since_calibration = 0
        self.update_ui_for_gesture()
        self.enter_calibration_state()
        self.setFocus()

    def enter_calibration_state(self):
        """进入校准等待状态"""
        if not self.info_locked: return
        self.needs_calibration = True
        self.samples_since_calibration = 0
        self.lbl_instruction.setText("Relax Hand -> Press [C]")
        self.lbl_instruction.setStyleSheet(f"color: {COLOR_APPLE_RED}; margin-bottom: 20px;")
        self.lbl_status_indicator.setText("Wait Calib")
        self.lbl_status_indicator.setStyleSheet(f"background-color: {COLOR_APPLE_ORANGE}; color: white; border-radius: 50px; font-family: \"{UI_FONT_FAMILY}\"; font-weight: bold;")

    def enter_capture_state(self):
        """进入采集准备状态"""
        self.needs_calibration = False
        self.lbl_instruction.setText("Hold Pose -> Press [Space]")
        self.lbl_instruction.setStyleSheet(f"color: {COLOR_APPLE_BLUE}; margin-bottom: 20px;")
        self.lbl_status_indicator.setText(f"Ready")
        self.lbl_status_indicator.setStyleSheet(f"background-color: {COLOR_APPLE_GREEN}; color: white; border-radius: 50px; font-family: \"{UI_FONT_FAMILY}\"; font-weight: bold;")

    def perform_calibration(self):
        """执行校准 (记录 R0)"""
        if not self.receiver.latest_reversed_data: return
        if len(self.data_buffer) >= 10:
            recent_frames = list(self.data_buffer)[-10:]
            avg_volts = np.mean([f['data'] for f in recent_frames], axis=0)
            self.current_R0 = [self.exo.voltage_to_resistance(v) for v in avg_volts]
        else:
            self.current_R0 = [self.exo.voltage_to_resistance(v) for v in self.receiver.latest_reversed_data]
        print(f"Calibration Done.")
        self.enter_capture_state()

    def start_capture_gesture(self):
        """开始采集数据"""
        if self.is_collecting: return
        self.is_collecting = True
        self.start_capture_time = time.time()
        self.temp_capture_data = []
        # 回溯一点数据
        cutoff = self.start_capture_time - PRE_CAPTURE_DURATION
        for item in self.data_buffer:
            if item['timestamp'] >= cutoff:
                self.temp_capture_data.append(item)
        self.lbl_instruction.setText("Collecting...")
        self.lbl_instruction.setStyleSheet(f"color: {COLOR_APPLE_GREEN}; margin-bottom: 20px;")
        self.collection_timer.start(20)

    def check_capture_status(self):
        """定时器回调：检查采集进度"""
        if not self.is_collecting: return
        elapsed = time.time() - self.start_capture_time
        pct = int(elapsed / CAPTURE_DURATION * 100)
        self.capture_progress.setValue(min(pct, 100))
        if elapsed >= CAPTURE_DURATION:
            self.stop_capture()

    def stop_capture(self):
        """停止采集并保存"""
        self.is_collecting = False
        self.collection_timer.stop()
        self.capture_progress.setValue(100)
        self.save_data_to_csv()
        self.gesture_progress[self.current_gesture_idx] += 1
        self.current_rep_count = self.gesture_progress[self.current_gesture_idx]
        self.samples_since_calibration += 1
        self.update_grid_status()

        if self.current_rep_count >= TOTAL_REPS_PER_GESTURE:
            self.lbl_instruction.setText("Done! Press [->]")
            self.lbl_instruction.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; margin-bottom: 20px;")
            self.lbl_status_indicator.setText("Completed")
            self.needs_calibration = True
        elif self.samples_since_calibration >= CALIBRATION_INTERVAL:
            self.enter_calibration_state()
        else:
            self.lbl_instruction.setText("Relax -> Press [Space]")
            self.lbl_instruction.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; margin-bottom: 20px;")

    def save_data_to_csv(self):
        """保存 CSV 文件"""
        if not self.temp_capture_data or self.current_R0 is None: return
        name = self.input_name.text().strip() or "Unknown"
        gender = self.combo_gender.currentText()
        size = self.combo_size.currentText()
        user_dir = os.path.join(self.save_dir_base, f"{name}_{gender}_{size}")
        if not os.path.exists(user_dir): os.makedirs(user_dir)

        g_idx = self.current_gesture_idx + 1
        g_name = GESTURE_LIST[self.current_gesture_idx].replace(" ", "_")
        rep = self.current_rep_count + 1
        ts_str = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{user_dir}/{g_idx:02d}_{g_name}_rep{rep:02d}_{ts_str}.csv"
        t0 = self.temp_capture_data[0]['timestamp']

        try:
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                headers = ["Time(s)"]
                for i in range(1, TOTAL_CELLS+1): headers.append(f"R_raw_{i}")
                for i in range(1, TOTAL_CELLS+1): headers.append(f"dR_ratio_{i}")
                writer.writerow(headers)
                for frame in self.temp_capture_data:
                    t_curr = frame['timestamp'] - t0
                    volts = frame['data']
                    rs = [self.exo.voltage_to_resistance(v) for v in volts]
                    dRs = [((r - self.current_R0[i])/self.current_R0[i] if self.current_R0[i]>1e-3 else 0) for i,r in enumerate(rs)]
                    row = [f"{t_curr:.4f}"] + [f"{val:.2f}" for val in rs] + [f"{val:.4f}" for val in dRs]
                    writer.writerow(row)
            print(f"Saved: {filename}")
        except Exception as e: print(e)

    def update_ui_for_gesture(self):
        """更新 UI 显示当前手势"""
        idx = self.current_gesture_idx
        self.lbl_gesture_name.setText(f"{idx+1}. {GESTURE_LIST[idx]}")
        self.load_gesture_image(idx)
        self.capture_progress.setValue(0)
        self.update_grid_status()

    def update_grid_status(self):
        """更新所有任务格子的状态"""
        total_completed = sum(self.gesture_progress.values())
        total_tasks = len(GESTURE_LIST) * TOTAL_REPS_PER_GESTURE
        for i, cell in enumerate(self.gesture_cells):
            cell.update_status(self.gesture_progress[i], i == self.current_gesture_idx)
        self.lbl_total_progress.setText(f"{total_completed} / {total_tasks} Completed")

    # 【注意！核心坑点：数据到达时的处理】
    def on_data_received(self, data, fps):
        self.lbl_fps.setText(f"FPS: {fps:.1f}")
        ts = time.time()
        self.data_buffer.append({'timestamp': ts, 'data': data})
        if self.is_collecting: self.temp_capture_data.append({'timestamp': ts, 'data': data})

        # 更新传感器热力图
        for i, val in enumerate(data):
            if i < len(self.sensor_cells):
                norm = min(max(val/3300, 0), 1)
                c = int(255*(1-norm))

                # 【关键修改点 5】左侧传感器格子的更新样式
                # 必须在这里再次设置 font-family: "{UI_FONT_FAMILY}" 和 font-size: 36px，否则会被覆盖！
                self.sensor_cells[i].setStyleSheet(f"background-color: rgb(255,{c},{c}); border-radius: 8px; font-family: \"{UI_FONT_FAMILY}\"; font-size: 36px; font-weight: bold; color: black;")
                self.sensor_cells[i].setText(f"{int(val)}")

    def closeEvent(self, event):
        self.worker.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_socket.bind((HOST, PORT))
        server_socket.listen(1)
        print(f"Listening on {PORT}...")
        conn, addr = server_socket.accept()
        conn.setblocking(False)
        window = GestureCollectionWindow(conn)
        window.show()
        sys.exit(app.exec_())
    except Exception as e: print(e)
    finally: server_socket.close()
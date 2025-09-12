import os
import sys
import json
from datetime import datetime
import numpy as np
import open3d as o3d
from smplx import MANO
import torch
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from mpl_toolkits.mplot3d import Axes3D

class MANOControlWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MANO Hand Controller")
        self.setGeometry(100, 100, 1400, 900)

        # 初始化参数
        self.pca_values = [0.0] * 45
        self.saved_states = {}

        # 创建主窗口部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 创建主布局
        main_layout = QHBoxLayout(central_widget)

        # 创建左侧控制面板
        control_panel = self.create_control_panel()
        main_layout.addWidget(control_panel, stretch=1)

        # 创建右侧3D视图
        self.viewer = MANOViewerWidget()
        main_layout.addWidget(self.viewer, stretch=2)

        # 加载MANO模型
        if not self.load_mano_model():
            return

        # 初始化显示
        self.update_hand_model()

    def create_control_panel(self):
        """创建控制面板"""
        panel = QWidget()
        panel.setMinimumWidth(300)
        layout = QVBoxLayout(panel)
        layout.setSpacing(5)

        # 标题
        title = QLabel("MANO Hand Controller")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin: 15px 0px; color: #333;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 滚动区域用于放置滑动条
        scroll_area = QScrollArea()
        scroll_area.setStyleSheet("QScrollArea { border: none; }")
        scroll_widget = QWidget()
        self.sliders_layout = QVBoxLayout(scroll_widget)
        self.sliders_layout.setSpacing(2)

        # 创建45个滑动条
        self.sliders = []
        for i in range(45):
            slider_group = QFrame()
            slider_group.setStyleSheet("""
                QFrame {
                    background-color: #f8f9fa;
                    border: 1px solid #e9ecef;
                    border-radius: 5px;
                    margin: 2px 0;
                }
            """)
            slider_layout = QHBoxLayout(slider_group)
            slider_layout.setContentsMargins(8, 5, 8, 5)

            # 标签
            label = QLabel(f"PCA {i:02d}")
            label.setFixedWidth(50)
            label.setStyleSheet("font-weight: bold; color: #495057;")

            # 滑动条
            slider = QSlider(Qt.Horizontal)
            slider.setMinimum(-100)
            slider.setMaximum(100)
            slider.setValue(0)
            slider.setTickPosition(QSlider.TicksBelow)
            slider.setTickInterval(25)
            slider.setStyleSheet("""
                QSlider::groove:horizontal {
                    height: 6px;
                    background: #dee2e6;
                    border-radius: 3px;
                }
                QSlider::handle:horizontal {
                    background: #007bff;
                    border: 1px solid #0056b3;
                    width: 18px;
                    margin: -6px 0;
                    border-radius: 9px;
                }
                QSlider::sub-page:horizontal {
                    background: #007bff;
                    border-radius: 3px;
                }
            """)
            slider.valueChanged.connect(lambda value, idx=i: self.on_slider_changed(idx, value))
            self.sliders.append(slider)

            # 数值显示
            value_label = QLabel("0.00")
            value_label.setFixedWidth(40)
            value_label.setAlignment(Qt.AlignCenter)
            value_label.setStyleSheet("background-color: #e9ecef; border-radius: 3px; padding: 2px;")
            setattr(self, f"value_label_{i}", value_label)

            slider_layout.addWidget(label)
            slider_layout.addWidget(slider)
            slider_layout.addWidget(value_label)

            self.sliders_layout.addWidget(slider_group)

        scroll_widget.setLayout(self.sliders_layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("color: #ddd;")
        layout.addWidget(line)

        # 控制按钮区域
        buttons_widget = QWidget()
        buttons_layout = QVBoxLayout(buttons_widget)
        buttons_layout.setSpacing(8)

        # 重置按钮
        self.reset_btn = QPushButton("Reset All Sliders")
        self.reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                font-weight: bold;
                padding: 12px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            QPushButton:pressed {
                background-color: #bd2130;
            }
        """)
        self.reset_btn.clicked.connect(self.reset_all_sliders)
        buttons_layout.addWidget(self.reset_btn)

        # 保存按钮
        self.save_btn = QPushButton("Save Current State")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                padding: 12px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:pressed {
                background-color: #1e7e34;
            }
        """)
        self.save_btn.clicked.connect(self.save_current_state)
        buttons_layout.addWidget(self.save_btn)

        # 加载按钮
        self.load_btn = QPushButton("Load Selected State")
        self.load_btn.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                font-weight: bold;
                padding: 12px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #0069d9;
            }
            QPushButton:pressed {
                background-color: #0062cc;
            }
        """)
        self.load_btn.clicked.connect(self.load_saved_state)
        buttons_layout.addWidget(self.load_btn)

        layout.addWidget(buttons_widget)

        # 状态管理区域
        state_widget = QWidget()
        state_layout = QVBoxLayout(state_widget)
        state_layout.setSpacing(5)

        # 状态选择下拉菜单
        state_label = QLabel("Saved States:")
        state_label.setStyleSheet("font-weight: bold; color: #495057;")
        state_layout.addWidget(state_label)

        self.state_combo = QComboBox()
        self.state_combo.addItem("Select a saved state...")
        self.state_combo.setStyleSheet("""
            QComboBox {
                padding: 8px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                background: white;
            }
            QComboBox::drop-down {
                border: none;
            }
        """)
        state_layout.addWidget(self.state_combo)

        # 删除状态按钮
        self.delete_btn = QPushButton("Delete Selected State")
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffc107;
                color: #212529;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
                border: none;
            }
            QPushButton:hover {
                background-color: #e0a800;
            }
            QPushButton:pressed {
                background-color: #d39e00;
            }
        """)
        self.delete_btn.clicked.connect(self.delete_saved_state)
        state_layout.addWidget(self.delete_btn)

        layout.addWidget(state_widget)

        # 状态信息
        self.state_info = QLabel("States saved: 0")
        self.state_info.setAlignment(Qt.AlignCenter)
        self.state_info.setStyleSheet("color: #6c757d; font-size: 12px; margin: 10px 0;")
        layout.addWidget(self.state_info)

        return panel

    def load_mano_model(self):
        """加载MANO模型"""
        model_path = '../MANO_RIGHT.pkl'

        if not os.path.exists(model_path):
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("Error")
            msg.setText(f"MANO model file not found: {model_path}")
            msg.setInformativeText("Please make sure the MANO_RIGHT.pkl file is in the current directory.")
            msg.setStyleSheet("""
                QMessageBox {
                    font-family: 'Segoe UI';
                }
            """)
            msg.exec_()
            return False

        try:
            self.mano_model = MANO(model_path=model_path, is_rhand=True, num_pca_comps=45)
            return True
        except Exception as e:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("Error")
            msg.setText("Failed to load MANO model")
            msg.setInformativeText(str(e))
            msg.setStyleSheet("""
                QMessageBox {
                    font-family: 'Segoe UI';
                }
            """)
            msg.exec_()
            return False

    def on_slider_changed(self, index, value):
        """滑动条值改变时的回调函数"""
        # 将-100~100的值转换为-3.0~3.0
        self.pca_values[index] = value / 100.0 * 3.0

        # 更新数值显示
        value_label = getattr(self, f"value_label_{index}")
        value_label.setText(f"{self.pca_values[index]:.2f}")

        # 更新手部模型
        self.update_hand_model()

    def update_hand_model(self):
        """更新手部模型显示"""
        if not hasattr(self, 'mano_model'):
            return

        try:
            # 生成手部姿态数据
            hand_pose = torch.tensor(self.pca_values).view(1, -1).float()

            # 计算手部网格
            output = self.mano_model(
                betas=torch.zeros([1, 10]),
                hand_pose=hand_pose,
                global_orient=torch.zeros([1, 3])
            )

            vertices = output.vertices.detach().cpu().numpy()[0]
            faces = self.mano_model.faces.astype(np.int32)

            # 更新3D视图
            self.viewer.update_mesh(vertices, faces)

        except Exception as e:
            print(f"Error updating hand model: {e}")

    def reset_all_sliders(self):
        """重置所有滑动条"""
        reply = QMessageBox.question(self, 'Reset Confirmation',
                                     'Are you sure you want to reset all sliders to zero?',
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            for i, slider in enumerate(self.sliders):
                slider.setValue(0)
                self.pca_values[i] = 0.0
                value_label = getattr(self, f"value_label_{i}")
                value_label.setText("0.00")
            self.update_hand_model()

    def save_current_state(self):
        """保存当前状态"""
        name, ok = QInputDialog.getText(self, "Save State", "Enter a name for this state:")
        if ok and name:
            if name in self.saved_states:
                reply = QMessageBox.question(self, 'Overwrite Confirmation',
                                             f'State "{name}" already exists. Overwrite?',
                                             QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply == QMessageBox.No:
                    return

            # 保存当前状态
            self.saved_states[name] = {
                'values': self.pca_values.copy(),
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            # 更新下拉菜单
            if self.state_combo.findText(name) == -1:
                self.state_combo.addItem(name)

            # 更新状态信息
            self.state_info.setText(f"States saved: {len(self.saved_states)}")

            QMessageBox.information(self, "Success", f"State '{name}' saved successfully!")

    def load_saved_state(self):
        """加载保存的状态"""
        if self.state_combo.currentIndex() == 0:
            QMessageBox.warning(self, "Warning", "Please select a saved state from the dropdown!")
            return

        state_name = self.state_combo.currentText()
        if state_name in self.saved_states:
            state_data = self.saved_states[state_name]
            values = state_data['values']

            # 更新PCA值和滑动条
            self.pca_values = values.copy()

            for i, value in enumerate(values):
                # 将-3.0~3.0的值转换为-100~100
                slider_value = int(value / 3.0 * 100)
                self.sliders[i].setValue(slider_value)
                value_label = getattr(self, f"value_label_{i}")
                value_label.setText(f"{value:.2f}")

            self.update_hand_model()
            QMessageBox.information(self, "Success", f"State '{state_name}' loaded successfully!\nSaved: {state_data['timestamp']}")
        else:
            QMessageBox.warning(self, "Warning", "Selected state not found!")

    def delete_saved_state(self):
        """删除保存的状态"""
        if self.state_combo.currentIndex() == 0:
            QMessageBox.warning(self, "Warning", "Please select a saved state to delete!")
            return

        state_name = self.state_combo.currentText()
        if state_name in self.saved_states:
            reply = QMessageBox.question(self, 'Delete Confirmation',
                                         f'Are you sure you want to delete state "{state_name}"?',
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

            if reply == QMessageBox.Yes:
                # 删除状态
                del self.saved_states[state_name]

                # 从下拉菜单中移除
                index = self.state_combo.findText(state_name)
                if index != -1:
                    self.state_combo.removeItem(index)

                # 更新状态信息
                self.state_info.setText(f"States saved: {len(self.saved_states)}")

                QMessageBox.information(self, "Success", f"State '{state_name}' deleted successfully!")

class MANOViewerWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(500, 500)
        self.setStyleSheet("""
            QWidget {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 8px;
            }
        """)

        # 创建matplotlib图形
        self.figure = plt.Figure(figsize=(5, 5), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.ax = None

        # 初始化变量
        self.vertices = None
        self.faces = None

        # 布局
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.canvas)
        self.setLayout(layout)

        # 初始化3D轴
        self.initialize_plot()

        # 更新定时器
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(100)  # 100ms更新一次

    def initialize_plot(self):
        """初始化3D绘图"""
        try:
            self.ax = self.figure.add_subplot(111, projection='3d')
            self.ax.set_facecolor('white')
            self.ax.grid(True)
            self.ax.set_title('MANO Hand Model', fontsize=12, pad=20)
            self.ax.set_xlabel('X')
            self.ax.set_ylabel('Y')
            self.ax.set_zlabel('Z')

            # 设置相等的轴比例
            self.ax.set_xlim([-0.1, 0.1])
            self.ax.set_ylim([-0.1, 0.1])
            self.ax.set_zlim([-0.1, 0.1])

            self.canvas.draw()
        except Exception as e:
            print(f"Error initializing plot: {e}")

    def update_mesh(self, vertices, faces):
        """更新网格数据"""
        self.vertices = vertices.copy()
        self.faces = faces.copy()

    def update_plot(self):
        """更新3D绘图"""
        if self.vertices is None or self.faces is None or self.ax is None:
            return

        try:
            # 清除当前图形
            self.ax.clear()

            # 绘制网格
            if len(self.vertices) > 0 and len(self.faces) > 0:
                # 绘制面
                for face in self.faces:
                    if len(face) >= 3:
                        triangle = self.vertices[face[:3]]
                        # 创建三角形
                        xs = triangle[:, 0]
                        ys = triangle[:, 1]
                        zs = triangle[:, 2]
                        # 闭合三角形
                        xs = np.append(xs, xs[0])
                        ys = np.append(ys, ys[0])
                        zs = np.append(zs, zs[0])
                        self.ax.plot(xs, ys, zs, 'b-', linewidth=0.5, alpha=0.3)

                # 绘制顶点
                self.ax.scatter(self.vertices[:, 0], self.vertices[:, 1], self.vertices[:, 2],
                                c='lightblue', s=10, alpha=0.6)

            # 设置标签和标题
            self.ax.set_title('MANO Hand Model', fontsize=12, pad=20)
            self.ax.set_xlabel('X')
            self.ax.set_ylabel('Y')
            self.ax.set_zlabel('Z')

            # 设置相等的轴比例
            if len(self.vertices) > 0:
                x_range = [self.vertices[:, 0].min(), self.vertices[:, 0].max()]
                y_range = [self.vertices[:, 1].min(), self.vertices[:, 1].max()]
                z_range = [self.vertices[:, 2].min(), self.vertices[:, 2].max()]

                # 增加一些边距
                margin = 0.05
                x_range = [x_range[0] - margin, x_range[1] + margin]
                y_range = [y_range[0] - margin, y_range[1] + margin]
                z_range = [z_range[0] - margin, z_range[1] + margin]

                self.ax.set_xlim(x_range)
                self.ax.set_ylim(y_range)
                self.ax.set_zlim(z_range)

            # 更新画布
            self.canvas.draw()

        except Exception as e:
            print(f"Error updating plot: {e}")

def main():
    # 确保在主线程中运行
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication(sys.argv)

    # 设置应用程序样式
    app.setStyle('Fusion')

    # 设置调色板
    palette = app.palette()
    palette.setColor(QPalette.Window, QColor(248, 249, 250))
    palette.setColor(QPalette.Base, QColor(255, 255, 255))
    palette.setColor(QPalette.AlternateBase, QColor(240, 240, 240))
    app.setPalette(palette)

    # 设置应用程序字体
    font = QFont("Segoe UI", 9)
    app.setFont(font)

    # 创建主窗口
    window = MANOControlWindow()
    window.show()

    # 运行应用程序
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

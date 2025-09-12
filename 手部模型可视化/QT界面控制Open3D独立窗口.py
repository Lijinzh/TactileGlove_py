import os
import numpy as np
import open3d as o3d
from smplx import MANO
import torch
import threading
import time
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

class MANOHandVisualizer:
    """
    MANO手部可视化器类
    用于接收45维PCA数据并进行3D可视化
    """

    def __init__(self, model_path_right='MANO_RIGHT.pkl', model_path_left='MANO_LEFT.pkl', is_rhand=True):
        """
        初始化MANO手部可视化器

        :param model_path_right: 右手MANO模型文件路径
        :param model_path_left: 左手MANO模型文件路径
        :param is_rhand: 是否为右手（True为右手，False为左手）
        """
        # 选择模型路径：根据is_rhand参数选择使用左手或右手模型
        model_path = model_path_right if is_rhand else model_path_left

        # 检查模型文件是否存在，不存在则抛出异常
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file {model_path} does not exist.")

        # 加载 MANO 模型
        # num_pca_comps=45 表示使用45个PCA分量来表示手部姿态
        self.mano_model = MANO(model_path=model_path, is_rhand=is_rhand, num_pca_comps=45)
        self.is_rhand = is_rhand  # 保存手部类型信息

        # 初始化 Open3D 网格对象：用于存储和显示3D手部网格
        self.mesh = o3d.geometry.TriangleMesh()
        self.line_set = None  # 用于显示网格线框

        # 初始化手部姿态为零（默认展开状态）
        self.reset_hand()

        # 初始化 Open3D 可视化器：创建可视化窗口
        self.vis = None
        self.window_created = False

        # 线程相关
        self.running = False
        self.update_lock = threading.Lock()
        self.latest_pose = np.zeros(45)

    def reset_hand(self):
        """
        重置手部到默认姿态（完全展开状态）
        使用零值参数调用MANO模型生成默认手部形状
        """
        # 调用MANO模型生成默认手部
        output = self.mano_model(
            betas=torch.zeros([1, 10]),  # 形状参数设为零（标准手型）
            hand_pose=torch.zeros([1, 45]),  # 手部姿态参数设为零（完全展开）
            global_orient=torch.zeros([1, 3])  # 全局朝向设为零
        )

        # 提取顶点坐标和面片信息
        vertices = output.vertices.detach().cpu().numpy()[0]  # 转换为numpy数组，选择第一个batch
        faces = self.mano_model.faces.astype(np.int32)  # 获取面片索引

        # 更新网格的顶点和面片信息
        self.mesh.vertices = o3d.utility.Vector3dVector(vertices)
        self.mesh.triangles = o3d.utility.Vector3iVector(faces)
        self.mesh.compute_vertex_normals()  # 计算法向量用于光照计算
        self.mesh.paint_uniform_color([0.7, 0.7, 0.7])  # 设置灰色显示

        # 创建线框
        self.create_wireframe(vertices, faces)

    def create_wireframe(self, vertices, faces):
        """创建线框几何体"""
        # 从面片中提取边
        edges = set()
        for face in faces:
            for i in range(3):
                edge = tuple(sorted([face[i], face[(i+1)%3]]))
                edges.add(edge)

        # 创建线集合
        lines = list(edges)
        self.line_set = o3d.geometry.LineSet()
        self.line_set.points = o3d.utility.Vector3dVector(vertices)
        self.line_set.lines = o3d.utility.Vector2iVector(lines)
        self.line_set.paint_uniform_color([0, 0, 0])  # 黑色线框

    def update_hand_pose(self, hand_pose_45d):
        """
        从45维PCA数据更新手部姿态

        :param hand_pose_45d: np.array，长度为45的PCA姿态数据
        """
        if len(hand_pose_45d) != 45:
            raise ValueError("输入数组长度必须为45")

        with self.update_lock:
            self.latest_pose = hand_pose_45d.copy()

    def create_window(self):
        """创建Open3D可视化窗口"""
        if self.window_created:
            return

        try:
            self.vis = o3d.visualization.Visualizer()
            self.vis.create_window(width=800, height=600, window_name='MANO Hand - Open3D Viewer')
            self.vis.add_geometry(self.mesh)  # 将网格添加到可视化器中
            if self.line_set:
                self.vis.add_geometry(self.line_set)  # 添加线框

            # 设置渲染选项：配置可视化器的显示效果
            render_opt = self.vis.get_render_option()
            render_opt.mesh_show_wireframe = False  # 不显示默认线框
            render_opt.background_color = [1, 1, 1]  # 白色背景
            render_opt.light_on = True  # 启用光照
            render_opt.line_width = 1.0  # 线宽

            self.window_created = True

            # 等待窗口完全创建
            time.sleep(0.1)

            # 设置相机视角：配置初始观察角度
            ctr = self.vis.get_view_control()
            ctr.set_zoom(0.8)  # 缩放级别
            ctr.set_lookat([0, 0, 0])  # 观察中心点
            ctr.set_up([0, -1, 0])  # 上方向向量
            ctr.set_front([0, 0, -1])  # 观察方向向量

        except Exception as e:
            print(f"Error creating Open3D window: {e}")

    def run_visualization(self):
        """运行可视化主循环"""
        self.create_window()
        if not self.window_created:
            return

        self.running = True

        # 主循环
        while self.running and self.vis.poll_events():
            try:
                # 检查是否有新的姿态数据
                with self.update_lock:
                    current_pose = self.latest_pose.copy()

                # 更新手部网格
                hand_pose_tensor = torch.tensor(current_pose).view(1, -1).float()

                output = self.mano_model(
                    betas=torch.zeros([1, 10]),  # 保持标准手型
                    hand_pose=hand_pose_tensor,  # 使用计算得到的姿态参数
                    global_orient=torch.zeros([1, 3])  # 保持默认朝向
                )

                # 提取新的顶点坐标
                new_vertices = output.vertices.detach().cpu().numpy()[0]

                # 更新网格顶点
                self.mesh.vertices = o3d.utility.Vector3dVector(new_vertices)
                self.mesh.compute_vertex_normals()  # 重新计算法向量

                # 更新线框
                if self.line_set:
                    self.line_set.points = o3d.utility.Vector3dVector(new_vertices)

                # 更新可视化网格
                self.vis.update_geometry(self.mesh)
                if self.line_set:
                    self.vis.update_geometry(self.line_set)
                self.vis.update_renderer()

                # 短暂休眠以控制帧率
                time.sleep(0.016)  # 约60 FPS

            except Exception as e:
                print(f"Error in visualization loop: {e}")
                break

        # 清理资源
        if self.vis:
            self.vis.destroy_window()

    def stop(self):
        """停止可视化"""
        self.running = False

class MANOControlWindow(QMainWindow):
    def __init__(self, visualizer):
        super().__init__()
        self.visualizer = visualizer
        self.setWindowTitle("MANO Hand Controller - 45D PCA")
        self.setGeometry(100, 100, 400, 800)  # 调整窗口大小，只保留控制面板

        # 初始化参数
        self.pca_values = [0.0] * 45
        self.saved_states = {}

        # 创建主窗口部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 创建主布局（现在只有一列）
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)

        # 创建控制面板
        control_panel = self.create_control_panel()
        main_layout.addWidget(control_panel)

        # 初始化显示
        self.update_hand_model()

    def create_control_panel(self):
        """创建控制面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(5)

        # 标题
        title = QLabel("MANO Hand Controller\n(45D PCA)")
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
        # 将PCA值转换为numpy数组并更新可视化器
        pose_array = np.array(self.pca_values)
        self.visualizer.update_hand_pose(pose_array)

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
                'timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
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

    def closeEvent(self, event):
        """窗口关闭事件"""
        self.visualizer.stop()
        event.accept()

def main():
    import sys

    # 检查MANO模型文件
    model_path = 'MANO_RIGHT.pkl'
    if not os.path.exists(model_path):
        print(f"Error: MANO model file '{model_path}' not found!")
        print("Please download the MANO model and place it in the current directory.")
        return

    # 创建可视化器
    try:
        visualizer = MANOHandVisualizer(is_rhand=True)
    except Exception as e:
        print(f"Error creating visualizer: {e}")
        return

    # 启动Open3D可视化线程
    vis_thread = threading.Thread(target=visualizer.run_visualization, daemon=True)
    vis_thread.start()

    # 等待窗口创建完成
    timeout = 0
    while not visualizer.window_created and timeout < 100:  # 增加超时机制
        time.sleep(0.1)
        timeout += 1

    # 创建Qt应用程序
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
    window = MANOControlWindow(visualizer)
    window.show()

    # 运行应用程序
    try:
        sys.exit(app.exec_())
    except Exception as e:
        print(f"Application error: {e}")
    finally:
        visualizer.stop()

if __name__ == "__main__":
    main()

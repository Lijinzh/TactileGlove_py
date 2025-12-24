# robot_gui_monitor.py
# Description:
# The frontend GUI for monitoring the IMU and controlling the robot.
# It reads data from the shared state object and handles keyboard inputs
# to update the shared state, commanding the backend controller.

import sys
import numpy as np

import pyqtgraph as pg
import pyqtgraph.opengl as gl
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont, QPalette, QColor

# --- Import the shared state object ---
from shared_state import shared_state

class PoseVisualizer3D(QMainWindow):
    """The main GUI window for monitoring and interaction."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle('FR3 Robot Monitor (按住空格激活)')
        self.setGeometry(100, 100, 1400, 900)
        self._setup_ui()

        self.timer = QTimer()
        self.timer.setInterval(33) # ~30 FPS refresh rate
        self.timer.timeout.connect(self.update_ui)
        self.timer.start()

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        self.view3d = gl.GLViewWidget()
        self.view3d.setCameraPosition(distance=5)
        main_layout.addWidget(self.view3d, stretch=3)
        grid = gl.GLGridItem(); grid.scale(2, 2, 1); self.view3d.addItem(grid)
        verts = np.array([ [0.5, 0.5, 0.5], [0.5, 0.5, -0.5], [0.5, -0.5, 0.5], [0.5, -0.5, -0.5], [-0.5, 0.5, 0.5], [-0.5, 0.5, -0.5], [-0.5, -0.5, 0.5], [-0.5, -0.5, -0.5] ]) * np.array([1.0, 2.0, 0.2])
        faces = np.array([ [0, 2, 3], [0, 3, 1], [4, 5, 7], [4, 7, 6], [0, 1, 5], [0, 5, 4], [2, 6, 7], [2, 7, 3], [1, 3, 7], [1, 7, 5], [0, 4, 6], [0, 6, 2] ])
        colors = np.array([ [1, 0, 0, 1], [1, 0.5, 0, 1], [1, 1, 0, 1], [0.5, 1, 0, 1], [0, 1, 0, 1], [0, 1, 0.5, 1], [0, 1, 1, 1], [0, 0.5, 1, 1] ])
        self.mesh = gl.GLMeshItem(vertexes=verts, faces=faces, vertexColors=colors, smooth=False, drawEdges=True)
        self.view3d.addItem(self.mesh)

        data_panel = QWidget(); data_layout = QVBoxLayout(data_panel); main_layout.addWidget(data_panel, stretch=1)
        title_font = QFont(); title_font.setPointSize(16); title_font.setBold(True)
        data_font = QFont(); data_font.setPointSize(12)
        mono_font = QFont("Courier New"); mono_font.setPointSize(12)

        control_title = QLabel("控制状态 (Control)"); control_title.setFont(title_font); data_layout.addWidget(control_title)
        self.status_label = QLabel("状态: PENDING"); self.status_label.setFont(data_font); data_layout.addWidget(self.status_label)
        self.robot_conn_label = QLabel("机器人连接: PENDING"); self.robot_conn_label.setFont(data_font); data_layout.addWidget(self.robot_conn_label)
        help_label = QLabel("按住<SPACE>激活控制\n按<R>键重置IMU零位"); help_label.setFont(data_font); data_layout.addWidget(help_label)
        data_layout.addSpacing(20)

        pose_label = QLabel("IMU 姿态数据 (Pose)"); pose_label.setFont(title_font); data_layout.addWidget(pose_label)
        self.roll_label = QLabel("Roll:  0.0°"); self.roll_label.setFont(mono_font); data_layout.addWidget(self.roll_label)
        self.pitch_label = QLabel("Pitch: 0.0°"); self.pitch_label.setFont(mono_font); data_layout.addWidget(self.pitch_label)
        self.yaw_label = QLabel("Yaw:   0.0°"); self.yaw_label.setFont(mono_font); data_layout.addWidget(self.yaw_label)
        data_layout.addSpacing(20)

        cmd_label = QLabel("机械臂速度指令 (Command)"); cmd_label.setFont(title_font); data_layout.addWidget(cmd_label)
        self.vx_label = QLabel("vx: 0.000 m/s"); self.vx_label.setFont(mono_font); data_layout.addWidget(self.vx_label)
        self.vy_label = QLabel("vy: 0.000 m/s"); self.vy_label.setFont(mono_font); data_layout.addWidget(self.vy_label)
        self.vz_label = QLabel("vz: 0.000 m/s"); self.vz_label.setFont(mono_font); data_layout.addWidget(self.vz_label)
        self.wx_label = QLabel("wx: 0.000 rad/s"); self.wx_label.setFont(mono_font); data_layout.addWidget(self.wx_label)
        self.wy_label = QLabel("wy: 0.000 rad/s"); self.wy_label.setFont(mono_font); data_layout.addWidget(self.wy_label)
        self.wz_label = QLabel("wz: 0.000 rad/s"); self.wz_label.setFont(mono_font); data_layout.addWidget(self.wz_label)
        data_layout.addStretch()

    def update_ui(self):
        """Periodically reads from the shared state and updates the UI elements."""
        if not shared_state.is_running:
            self.close()
            return

        with shared_state.lock:
            euler = shared_state.latest_imu_euler
            cmd = shared_state.latest_velocity_command
            status = shared_state.controller_status
            robot_conn = shared_state.robot_connected

        transform = pg.Transform3D()
        transform.rotate(euler[2], 0, 0, 1); transform.rotate(euler[1], 0, 1, 0); transform.rotate(euler[0], 1, 0, 0)
        self.mesh.setTransform(transform)

        self.roll_label.setText(f"Roll:  {euler[0]:>6.1f}°")
        self.pitch_label.setText(f"Pitch: {euler[1]:>6.1f}°")
        self.yaw_label.setText(f"Yaw:   {euler[2]:>6.1f}°")
        self.vx_label.setText(f"vx: {cmd[0]:>+7.3f} m/s"); self.vy_label.setText(f"vy: {cmd[1]:>+7.3f} m/s"); self.vz_label.setText(f"vz: {cmd[2]:>+7.3f} m/s")
        self.wx_label.setText(f"wx: {cmd[3]:>+7.3f} rad/s"); self.wy_label.setText(f"wy: {cmd[4]:>+7.3f} rad/s"); self.wz_label.setText(f"wz: {cmd[5]:>+7.3f} rad/s")

        self.status_label.setText(f"状态: {status}")
        self.status_label.setStyleSheet("color: green; font-weight: bold;" if status == "ACTIVE" else "color: orange; font-weight: bold;")
        self.robot_conn_label.setText(f"机器人连接: {'CONNECTED' if robot_conn else 'FAILED'}")
        self.robot_conn_label.setStyleSheet("color: green;" if robot_conn else "color: red;")

    def keyPressEvent(self, event):
        if not event.isAutoRepeat():
            if event.key() == Qt.Key.Key_Space:
                with shared_state.lock: shared_state.control_active = True
            elif event.key() == Qt.Key.Key_R:
                with shared_state.lock: shared_state.reset_zero_pose_requested = True

    def keyReleaseEvent(self, event):
        if not event.isAutoRepeat() and event.key() == Qt.Key.Key_Space:
            with shared_state.lock: shared_state.control_active = False

    def closeEvent(self, event):
        print("GUI: Close event detected. Signaling controller to stop.")
        with shared_state.lock:
            shared_state.is_running = False
        event.accept()

if __name__ == '__main__':
    print("--- Starting Robot GUI Monitor (Frontend) ---")
    app = QApplication(sys.argv)

    dark_palette = QPalette()
    dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53)); dark_palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25)); dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white); dark_palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white); dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white); dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218)); dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
    app.setPalette(dark_palette)

    monitor = PoseVisualizer3D()
    monitor.show()
    sys.exit(app.exec())

import pybullet as p
import time
import pybullet_data

# 初始化物理引擎和可视化
physicsClient = p.connect(p.GUI)  # GUI模式

# 设置窗口大小（宽x高）
# p.configureDebugVisualizer(p.COV_ENABLE_GUI, 0)  # 禁用GUI控件
p.resetDebugVisualizerCamera(
    cameraDistance=0.5,  # 相机距离（使模型看起来更大）
    cameraYaw=0,  # 偏航角
    cameraPitch=-20,  # 俯仰角
    cameraTargetPosition=[0, 0, 0]  # 相机目标位置
)

p.setGravity(0, 0, -9.8)

# 加载 URDF 模型
p.setAdditionalSearchPath(pybullet_data.getDataPath())  # 添加数据路径
robot = p.loadURDF("mano.urdf", useFixedBase=True)

# 获取关节索引
joint_indices = {}
for i in range(p.getNumJoints(robot)):
    joint_info = p.getJointInfo(robot, i)
    joint_name = joint_info[1].decode("utf-8")
    joint_indices[joint_name] = i

# 定义动态配置序列
config_sequence = [
    {"j_index2": 0.0},
    {"j_index2": 0.5},
    {"j_index2": 1.0},
    {"j_index2": 0.5},
    {"j_index2": 0.0},
]

try:
    while True:
        # 逐步更新关节状态
        for cfg in config_sequence:
            for joint_name, value in cfg.items():
                joint_idx = joint_indices[joint_name]
                p.resetJointState(robot, joint_idx, value)
                for _ in range(10):  # 运行10步仿真，使动画更平滑
                    p.stepSimulation()
                    time.sleep(1. / 240.)  # 以240Hz的频率运行
except KeyboardInterrupt:
    pass

# 断开连接
p.disconnect()

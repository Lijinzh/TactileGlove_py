import pybullet as p
import time

# 初始化物理引擎和可视化
physicsClient = p.connect(p.GUI)  # GUI模式
p.setGravity(0, 0, -9.8)

# 加载 URDF 模型
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
# robot.show(cfg={
#     "j_index1y":    0.0,
#     "j_index1x":    0.0,
#     "j_index2":     0.0,
#     "j_index3":     0.0,
#     "j_middle1y":   0.0,
#     "j_middle1x":   0.0,
#     "j_middle2":    0.0,
#     "j_middle3":    0.0,
#     "j_pinky1y":    0.0,
#     "j_pinky1x":    0.0,
#     "j_pinky2":     0.0,
#     "j_pinky3":     0.0,
#     "j_ring1y":     0.0,
#     "j_ring1x":     0.0,
#     "j_ring2":      0.0,
#     "j_ring3":      0.0,
#     "j_thumb1y":    0.0,
#     "j_thumb1z":    0.0,
#     "j_thumb2":     0.0,
#     "j_thumb3":     0.0
# })
while True:
    # 逐步更新关节状态
    for cfg in config_sequence:
        for joint_name, value in cfg.items():
            joint_idx = joint_indices[joint_name]
            p.resetJointState(robot, joint_idx, value)
            time.sleep(0.1)  # 保持当前状态2秒
            p.stepSimulation()  # 更新物理仿真（可选）

# 断开连接
p.disconnect()

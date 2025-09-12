# 导入需要使用的库模块
import os
import numpy as np
import open3d as o3d
from smplx import MANO
import torch

# MANO手部关节的PCA参数映射说明
# MANO模型使用45个PCA分量来控制手部姿态，这些分量是通过对大量手部姿态数据进行主成分分析得到的
# 每个PCA分量都影响多个关节的组合运动
# 常见的控制方式是：
# - PCA分量0-2: 拇指相关
# - PCA分量3-8: 食指相关
# - PCA分量9-14: 中指相关
# - PCA分量15-20: 无名指相关
# - PCA分量21-26: 小指相关
# - PCA分量27-44: 其他复杂组合

def get_joint_control_data(joint_index, angle):
    """
    控制特定关节的方法
    joint_index: 关节索引 (0-14 对应15个主要关节自由度)
    angle: 关节角度 (-1.0 到 1.0 范围内)
    """
    # 创建一个零数组来存储所有关节控制数据
    joint_data = np.zeros(15)

    # 设置指定关节的角度
    if 0 <= joint_index < 15:
        joint_data[joint_index] = angle

    return joint_data

def get_pca_control_data(pca_index, value):
    """
    直接控制PCA分量的方法
    pca_index: PCA分量索引 (0-44)
    value: PCA分量值 (-3.0 到 3.0 范围较为合理)
    """
    # 创建一个零数组来存储所有PCA控制数据
    pca_data = np.zeros(45)

    # 设置指定PCA分量的值
    if 0 <= pca_index < 45:
        pca_data[pca_index] = value

    return pca_data

# 指定 MANO 右手模型文件路径
model_path = '../MANO_RIGHT.pkl'

# 检查 MANO 模型文件是否存在
if not os.path.exists(model_path):
    print(f"File {model_path} does not exist.")
    exit(1)

# 加载 MANO 模型
try:
    mano_model = MANO(model_path=model_path, is_rhand=True, num_pca_comps=45)
except Exception as e:
    print(f"Failed to load MANO model: {e}")
    exit(1)

# 初始化三角网格对象
mesh = o3d.geometry.TriangleMesh()

# 生成初始手部网格数据
output = mano_model(betas=torch.zeros([1, 10]),
                    hand_pose=torch.zeros([1, 45]),
                    global_orient=torch.zeros([1, 3]))

vertices = output.vertices.detach().cpu().numpy()[0]
faces = mano_model.faces.astype(np.int32)

mesh.vertices = o3d.utility.Vector3dVector(vertices)
mesh.triangles = o3d.utility.Vector3iVector(faces)

# 计算顶点法线以便平滑着色
mesh.compute_vertex_normals()
mesh.paint_uniform_color([0.7, 0.7, 0.7])

# 创建线框几何体
wireframe = o3d.geometry.LineSet.create_from_triangle_mesh(mesh)
wireframe.paint_uniform_color([0, 0, 0])

# 控制变量初始化
current_pca_index = 0  # 当前控制的PCA分量索引
current_pca_value = 0.0  # 当前PCA分量值
pca_step = 0.05  # PCA值变化步长
pca_direction = 1  # 变化方向

# 控制模式：0-按PCA分量控制，1-按关节控制
control_mode = 0  # 默认按PCA分量控制

def update_mesh(vis):
    global current_pca_index, current_pca_value, pca_step, pca_direction, control_mode

    try:
        if control_mode == 0:  # PCA分量控制模式
            # 更新当前PCA分量值
            current_pca_value += pca_step * pca_direction

            # 边界检测和方向反转
            if current_pca_value >= 2.0 or current_pca_value <= -2.0:
                pca_direction *= -1

            # 生成PCA控制数据
            pca_data = get_pca_control_data(current_pca_index, current_pca_value)
            hand_pose = torch.tensor(pca_data).view(1, -1).float()

        else:  # 关节控制模式
            # 这里只是一个示例，实际应用中你可以根据需要设置不同的关节
            joint_index = 7  # 例如控制第6个关节（中指根部）
            joint_angle = np.sin(current_pca_value)  # 使用正弦波模拟关节运动
            current_pca_value += 0.05

            # 生成关节控制数据
            joint_data = get_joint_control_data(joint_index, joint_angle)
            # 将15个关节数据扩展到45个PCA分量
            hand_pose = torch.tensor(np.tile(joint_data, 3)[:45]).view(1, -1).float()

        # 重新计算手模型的顶点位置
        output = mano_model(betas=torch.zeros([1, 10]),
                            hand_pose=hand_pose,
                            global_orient=torch.zeros([1, 3]))

        new_vertices = output.vertices.detach().cpu().numpy()[0]

        # 更新网格顶点和线框点
        mesh.vertices = o3d.utility.Vector3dVector(new_vertices)
        wireframe.points = mesh.vertices

        # 重新计算法线以保证着色效果正确
        mesh.compute_vertex_normals()

        # 更新可视化界面中的几何体
        vis.update_geometry(mesh)
        vis.update_geometry(wireframe)

    except Exception as e:
        print(f"Error during update: {e}")

def switch_pca_component(vis):
    """切换到下一个PCA分量"""
    global current_pca_index, current_pca_value
    current_pca_index = (current_pca_index + 1) % 45
    current_pca_value = 0.0
    print(f"Switched to PCA component: {current_pca_index}")

def switch_control_mode(vis):
    """切换控制模式"""
    global control_mode
    control_mode = 1 - control_mode
    mode_name = "Joint Control" if control_mode == 1 else "PCA Control"
    print(f"Switched to: {mode_name}")

def reset_hand(vis):
    """重置手部姿态"""
    global current_pca_value
    current_pca_value = 0.0
    print("Hand reset to neutral position")

# 创建Open3D可视化窗口
vis = o3d.visualization.VisualizerWithKeyCallback()
vis.create_window(width=800, height=600, window_name='MANO Hand Control Demo')

# 将网格和线框加入可渲染对象列表
vis.add_geometry(mesh)
vis.add_geometry(wireframe)

# 注册按键回调函数
vis.register_key_callback(ord('N'), switch_pca_component)  # N键切换PCA分量
vis.register_key_callback(ord('M'), switch_control_mode)   # M键切换控制模式
vis.register_key_callback(ord('R'), reset_hand)           # R键重置手部

# 设置渲染选项
render_opt = vis.get_render_option()
render_opt.mesh_show_wireframe = True
render_opt.background_color = [1, 1, 1]
render_opt.light_on = True

# 设置相机参数
ctr = vis.get_view_control()
ctr.set_zoom(0.8)
ctr.set_lookat([0, 0, 0.1])
ctr.set_up([0, -1, 0])
ctr.set_front([0, 0, -1])

# 显示操作说明
print("=" * 50)
print("MANO Hand Controller")
print("=" * 50)
print("N key: Switch to next PCA component")
print("M key: Switch between PCA/Joint control modes")
print("R key: Reset hand to neutral position")
print("Q key: Quit application")
print("\nCurrent mode: PCA Control")
print("Animating PCA component 0")
print("=" * 50)

# 主循环
while True:
    if not vis.poll_events():
        break
    update_mesh(vis)

# 退出程序时销毁窗口资源
vis.destroy_window()

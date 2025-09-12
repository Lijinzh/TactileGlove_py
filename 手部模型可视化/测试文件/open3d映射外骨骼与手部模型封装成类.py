import os
import numpy as np
import open3d as o3d
from smplx import MANO
import torch


class MANOHandVisualizer:
    """
    MANO手部可视化器类
    用于将24维手套数据映射到MANO手部模型并进行3D可视化
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
        self.wireframe = None  # 线框对象，用于显示网格边缘

        # 初始化手部姿态为零（默认展开状态）
        self.reset_hand()

        # 初始化 Open3D 可视化器：创建可视化窗口
        self.vis = o3d.visualization.VisualizerWithKeyCallback()
        self.vis.create_window(width=800, height=600, window_name='MANO Hand with Wireframe')
        self.vis.add_geometry(self.mesh)  # 将网格添加到可视化器中

        # 初始化线框标志：用于跟踪线框是否已添加
        self.wireframe_added = False

        # 设置渲染选项：配置可视化器的显示效果
        render_opt = self.vis.get_render_option()
        render_opt.mesh_show_wireframe = True  # 显示网格线框
        render_opt.background_color = [1, 1, 1]  # 白色背景
        render_opt.light_on = True  # 启用光照

        # 设置相机视角：配置初始观察角度
        ctr = self.vis.get_view_control()
        ctr.set_zoom(0.8)  # 缩放级别
        ctr.set_lookat([0, 0, 0.1])  # 观察中心点
        ctr.set_up([0, -1, 0])  # 上方向向量
        ctr.set_front([0, 0, -1])  # 观察方向向量

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
        vertices = output.vertices.detach().cpu().numpy()[0]  # 转换为numpy数组
        faces = self.mano_model.faces.astype(np.int32)  # 获取面片索引

        # 更新网格的顶点和面片信息
        self.mesh.vertices = o3d.utility.Vector3dVector(vertices)
        self.mesh.triangles = o3d.utility.Vector3iVector(faces)
        self.mesh.compute_vertex_normals()  # 计算法向量用于光照计算
        self.mesh.paint_uniform_color([0.7, 0.7, 0.7])  # 设置灰色显示

    def update_hand_pose(self, glove_data_24d):
        """
        从24维手套数据中提取15个关键自由度，并映射到正确的45维PCA空间
        实现手套数据到手部姿态的转换

        :param glove_data_24d: np.array，长度为24的手套传感器数据
        """
        # 数据验证：确保输入数据长度正确
        if len(glove_data_24d) != 24:
            raise ValueError("输入数组长度必须为24")

        # 提取15个关键自由度：从24维数据中选择最重要的15个维度
        # 这些索引对应手套传感器中最有代表性的关节自由度
        indices_15d = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 13, 14, 15, 16, 17]
        glove_data_15d = glove_data_24d[indices_15d]

        # 创建45维PCA向量并初始化为0
        # MANO模型使用45个PCA分量来描述手部姿态
        hand_pose_pca = np.zeros(45)

        # 定义15个自由度到45维PCA的映射关系
        # 每个手套自由度可能影响MANO模型中的多个PCA分量
        # 键为手套自由度索引，值为对应的PCA分量索引列表
        mapping_15_to_45 = {
            0: [1],  # 食指掌指关节外展内收 -> PCA 1 对
            1: [10],  # 中指掌指关节外展内收 -> PCA 2, 3 对
            2: [14, 17],  # 食指远节指间关节屈伸 -> PCA 4, 5 对
            3: [28],  # 食指掌指关节屈伸 -> PCA 6, 7 对
            4: [5, 8],  # 食指远节指间关节屈伸 -> PCA 8, 5 对
            5: [36, 38],  # 拇指腕掌关节外展内收 -> PCA 10, 11
            6: [37],  # 拇指腕掌关节屈伸 -> PCA 12, 13
            7: [2],  # 食指掌指关节屈伸 -> PCA 2 对
            8: [39],  # 拇指掌指关节屈伸 -> PCA 2对
            9: [43],  # 拇指指间关节屈伸 -> PCA 18, 19
            10: [19],  # 小拇指掌指关节外展内收 -> PCA 20, 21
            11: [32, 35],  # 无名指近节指间关节屈伸 -> PCA 22, 23
            12: [23, 26],  # 小指掌指关节外展内收 -> PCA 24, 25
            13: [29],  # 无名指掌指关节屈伸 -> PCA 26, 27 对
            14: [20]  # 小指掌指关节屈伸 -> PCA 28, 29 对
        }

        # 将15个手套自由度映射到对应的45维PCA分量
        # 每个手套自由度的值会被分配到相应的PCA分量中
        for i, pca_indices in mapping_15_to_45.items():
            # 获取当前手套自由度的角度值
            angle = glove_data_15d[i]
            # 将该角度值分配到所有对应的PCA分量中
            for idx in pca_indices:
                hand_pose_pca[idx] = angle

        # 转换为torch tensor：为MANO模型准备输入数据
        hand_pose_tensor = torch.tensor(hand_pose_pca).view(1, -1).float()

        # 调用MANO模型计算新的手部顶点坐标
        output = self.mano_model(
            betas=torch.zeros([1, 10]),  # 保持标准手型
            hand_pose=hand_pose_tensor,  # 使用计算得到的姿态参数
            global_orient=torch.zeros([1, 3])  # 保持默认朝向
        )
        # 提取新的顶点坐标
        new_vertices = output.vertices.detach().cpu().numpy()[0]

        # 更新网格顶点：用新计算的顶点替换原有顶点
        self.mesh.vertices = o3d.utility.Vector3dVector(new_vertices)
        self.mesh.compute_vertex_normals()  # 重新计算法向量

        # 更新线框显示：保持线框与网格同步
        if not self.wireframe_added:
            # 首次添加线框
            self.wireframe = o3d.geometry.LineSet.create_from_triangle_mesh(self.mesh)
            self.wireframe.paint_uniform_color([0, 0, 0])  # 黑色线框
            self.vis.add_geometry(self.wireframe)
            self.wireframe_added = True
        else:
            # 更新线框顶点位置
            self.wireframe.points = self.mesh.vertices
            self.vis.update_geometry(self.wireframe)

        # 更新可视化网格：通知可视化器网格已更新
        self.vis.update_geometry(self.mesh)

    def run(self):
        """
        运行可视化主循环
        持续处理窗口事件直到用户关闭窗口
        """
        print("Press Q to quit...")  # 提示用户按Q键退出
        # 持续处理事件循环
        while self.vis.poll_events():
            self.vis.update_renderer()  # 更新渲染
        self.vis.destroy_window()  # 清理资源


# 使用示例 - 平滑收缩张开动画（基于正确的映射关系）
if __name__ == "__main__":
    """
    主程序入口：演示手部可视化功能
    实现一个平滑的手指收缩张开动画效果
    """

    # 创建右手可视化器实例
    visualizer = MANOHandVisualizer(is_rhand=True)

    # 动画控制参数设置
    t = 0.0  # 时间参数，用于生成周期性动画
    speed = 0.05  # 动画速度控制参数
    amplitude = np.pi / 4  # 最大弯曲角度（π弧度约180度）

    # 主循环 - 实现平滑收缩张开动画
    print("Press Q in the visualization window to quit...")
    while visualizer.vis.poll_events():
        # 生成周期性变化的角度值：使用正弦函数创建平滑的开合效果
        # (np.sin(t) + 1) / 2 将正弦值从[-1,1]映射到[0,1]
        # 再乘以amplitude得到[0, π]范围的角度值
        angle = (np.sin(t) + 1) / 2 * amplitude  # 范围 [0, π]

        # 创建24维输入数组：模拟手套传感器数据
        glove_data_24d = np.zeros(24)  # 初始化为零

        # 设置关键的屈伸自由度来控制手指弯曲
        # 食指屈伸控制
        # glove_data_24d[2] = angle  # 食指近节指间关节屈伸
        # glove_data_24d[3] = angle  # 食指掌指关节屈伸
        # glove_data_24d[4] = angle  # 食指远节指间关节屈伸

        # 中指屈伸控制
        glove_data_24d[17] = angle  # 中指掌指关节外展内收（近似控制）
        # 可以继续添加更多手指的控制...

        # 更新手部姿态：将手套数据转换为手部网格
        visualizer.update_hand_pose(glove_data_24d)

        # 更新渲染：在可视化窗口中显示更新后的手部
        visualizer.vis.update_renderer()

        # 更新时间参数：推进动画时间，控制动画速度
        t += speed

    # 清理资源：关闭可视化窗口
    visualizer.vis.destroy_window()

import csv
import os
import config_utils


class StretchableExoskeleton:
    """可拉伸外骨骼类，用于计算电阻值和拉伸量"""

    def __init__(self):
        """初始化可拉伸外骨骼类"""
        self.initial_voltages = None  # 未拉伸状态的初始电压值
        self.pre_stretch_voltages = None  # 预拉伸状态的电压值
        self.initial_resistances = None  # 初始电阻值
        self.pre_stretch_resistances = None  # 预拉伸电阻值
        self.initial_stretch_ratios = None  # 初始拉伸比例（由于骨骼长度不同）

        # 传感器配置参数
        self.voltage_ref = config_utils.REFERENCE_VOLTAGE
        self.r_ref = config_utils.REFERENCE_RESISTANCE

    def voltage_to_resistance(self, voltage):
        """
        根据分压原理计算电阻值
        这里输入的电压实际上是ADS118测得的，经过INA185放大20倍增益的电压，所以需要先除以20
        使用公式: R = R_ref * (V_ref - V) / V
        其中 R_ref 是参考电阻，V_ref 是参考电压，V 是测量电压
        """
        # 注意这里的voltage_ref是小数，虽然在UI界面上面显示的是3300，实际上是3300.1这样子，所以如果是voltage > self.voltage_ref，那么就会判断为对，然后进入到下面等于0
        if voltage <= 0 or voltage > (self.voltage_ref + 1):
            return 0  # 避免除零错误和无效值
        resistance = self.voltage_ref / ((self.voltage_ref - voltage / 20) / self.r_ref) - self.r_ref
        return resistance

    def load_calibration_data(self, initial_file=None, pre_stretch_file=None):
        """
        读取校准数据CSV文件
        """

        def load_csv_data(filename, data_attr_name):
            """辅助函数：加载CSV数据"""
            if filename and os.path.exists(filename):
                try:
                    with open(filename, 'r') as csvfile:
                        reader = csv.reader(csvfile)
                        headers = next(reader)  # 跳过表头
                        data_row = next(reader)  # 读取数据行
                        voltages = [float(val) for val in data_row]
                        setattr(self, data_attr_name + '_voltages', voltages)
                        # 计算电阻值
                        resistances = [self.voltage_to_resistance(v) for v in voltages]
                        setattr(self, data_attr_name + '_resistances', resistances)
                        print(f"成功加载{data_attr_name}文件: {filename}")
                        return True
                except Exception as e:
                    print(f"读取{filename}时出错: {e}")
            else:
                print(f"未找到{data_attr_name}文件: {filename}")
            return False

        try:
            # 加载初始值文件
            load_csv_data(initial_file, 'initial')

            # 加载预拉伸值文件
            load_csv_data(pre_stretch_file, 'pre_stretch')

            # 计算初始拉伸比例（由于骨骼长度不同）
            if hasattr(self, 'initial_resistances') and hasattr(self, 'pre_stretch_resistances') and \
                    self.initial_resistances and self.pre_stretch_resistances:
                self.initial_stretch_ratios = []
                for i in range(len(self.initial_resistances)):
                    if self.initial_resistances[i] > 0:
                        ratio = (self.pre_stretch_resistances[i] - self.initial_resistances[i]) / \
                                self.initial_resistances[i]
                        self.initial_stretch_ratios.append(ratio)
                    else:
                        self.initial_stretch_ratios.append(0)
                print("成功计算初始拉伸比例")

        except Exception as e:
            print(f"加载校准数据时出错: {e}")

    def calculate_real_time_stretch(self, current_voltages):
        """
        计算实时拉伸量
        返回: (当前电阻值列表, 实时拉伸比例列表)
        """
        if not self.pre_stretch_resistances:
            return None, None

        # 计算当前电阻值
        current_resistances = [self.voltage_to_resistance(v) for v in current_voltages]

        # 计算实时拉伸比例：(当前电阻-预拉伸电阻)/预拉伸电阻
        real_time_stretch_ratios = []
        for i in range(len(current_resistances)):
            if self.pre_stretch_resistances[i] > 0:
                ratio = (current_resistances[i] - self.pre_stretch_resistances[i]) / self.pre_stretch_resistances[i]
                real_time_stretch_ratios.append(ratio)
            else:
                real_time_stretch_ratios.append(0)

        return current_resistances, real_time_stretch_ratios

    def get_initial_stretch_info(self):
        """获取初始拉伸信息"""
        return self.initial_stretch_ratios

    def is_calibrated(self):
        """检查是否已完成校准"""
        return self.initial_resistances is not None and self.pre_stretch_resistances is not None

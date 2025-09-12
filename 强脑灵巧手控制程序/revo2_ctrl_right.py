# 导入异步I/O库，用于处理异步操作
import asyncio
# 导入系统特定的参数和函数
import sys
# 导入时间访问和转换模块
import time
# 从自定义模块revo2_utils中导入硬件通信库libstark和日志记录器logger
from revo2_utils import libstark, logger

# 定义从设备ID为0x7f，表示右手设备
SLAVE_ID = 0x7f  # 右手
# 定义串口端口名称，注释掉的是Linux系统的USB串口格式
# PORT = "/dev/ttyUSB1" # 替换为实际的串口名称
# 实际使用的是Windows系统的COM5端口
PORT = "COM5"  # 替换为实际的串口名称
# 设置串口通信波特率为460800
BAUDRATE = libstark.Baudrate.Baud460800


# 定义异步主函数，使用async关键字表明这是一个协程
async def main():
    # 异步打开Modbus串口连接，返回一个设备上下文对象client
    # 使用await等待异步操作完成
    # 类型注解表明client是libstark.PyDeviceContext类型
    client: libstark.PyDeviceContext = await libstark.modbus_open(PORT, BAUDRATE)

    # 检查串口连接是否成功
    if not client:
        # 如果client为空，记录严重错误日志
        logger.critical(f"Failed to open serial port: {PORT}")
        # 退出程序，返回码1表示错误退出
        sys.exit(1)

    # 异步获取指定从设备的信息
    info = await client.get_device_info(SLAVE_ID)

    # 检查设备信息获取是否成功
    if not info:
        # 如果获取失败，记录严重错误日志
        logger.critical(f"Failed to get device info for right hand. Id: {SLAVE_ID}")
        # 退出程序，返回码1表示错误退出
        sys.exit(1)

    # 记录设备描述信息到日志
    logger.info(f"Right: {info.description}")

    # 设置手指单元模式为归一化模式
    await client.set_finger_unit_mode(SLAVE_ID, libstark.FingerUnitMode.Normalized)

    # 定义运动周期为2.0秒
    period = 2.0

    # 创建包含6个元素的列表，每个元素都是1000，代表6个手指的速度值
    speeds = [1000] * 6

    # 开始异常处理块
    try:
        # 无限循环，持续控制手指运动
        while True:
            # 获取当前时间戳（毫秒）
            now_ms = int(time.time() * 1000)

            # 计算当前时间在周期内的位置（秒）
            t = (now_ms / 1000.0) % period

            # 根据时间决定手指位置
            if t < period / 2:
                # 前半周期：所有手指位置为0（完全张开）
                positions = [0, 0, 0, 0, 0, 0]
            else:
                # 后半周期：部分手指位置为400或1000（部分或完全握紧）
                positions = [400, 0, 1000, 1000, 1000, 1000]

            # 记录当前发布的位置信息到日志
            logger.info(f"Publishing positions: {positions}")

            # 异步设置手指位置和速度
            await client.set_finger_positions_and_speeds(SLAVE_ID, positions, speeds)
            positions = client.get_finger_positions(SLAVE_ID)
            print(positions[0])

            # 异步睡眠0.01秒（10毫秒），控制循环频率
            await asyncio.sleep(0.01)

    # 捕获键盘中断异常（Ctrl+C）
    except KeyboardInterrupt:
        # 记录退出信息
        logger.info("Exiting...")

    # 异步关闭Modbus串口连接
    await libstark.modbus_close(client)

    # 正常退出程序，返回码0表示正常退出
    sys.exit(0)


# 程序入口点
if __name__ == "__main__":
    # 使用asyncio.run()运行异步主函数
    asyncio.run(main())

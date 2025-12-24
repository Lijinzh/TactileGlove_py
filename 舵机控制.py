import serial
import time
import re
# 有效范围0-70度
# === 配置区域 ===
SERIAL_PORT = 'COM9'
BAUD_RATE = 115200

def main():
    ser = None
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print(f"成功连接到 {SERIAL_PORT}")
        print("等待 ESP32 复位中...")
        time.sleep(2)
    except Exception as e:
        print(f"无法打开串口 {SERIAL_PORT}: {e}")
        return

    print("-" * 40)
    print("双舵机控制终端")
    print("输入格式：[夹爪数值] [舵机2角度]")
    print("示例：")
    print("  '0 90'   -> 夹爪打开，舵机2居中")
    print("  '70 0'   -> 夹爪关闭，舵机2转到0度")
    print("  '35 180' -> 夹爪半开，舵机2转到180度")
    print("输入 'q' 退出")
    print("-" * 40)

    try:
        while True:
            user_input = input("请输入指令 (例如 30 90 有效范围0-70度): ").strip()

            if user_input.lower() == 'q':
                break

            # 使用正则处理空格或逗号分隔
            # 这允许用户输入 "30 90" 或 "30,90"
            parts = re.split(r'[,\s]+', user_input)

            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                val1 = parts[0]
                val2 = parts[1]
                command = f"{val1},{val2}\n" # 转换为逗号分隔格式发送给 ESP32
            elif len(parts) == 1 and parts[0].isdigit():
                # 为了兼容单指令，默认第二个舵机保持不变（或发个默认值，这里仅发单个）
                val1 = parts[0]
                command = f"{val1}\n"
            else:
                print("格式错误！请输入两个数字，用空格隔开。")
                continue

            try:
                ser.write(command.encode('utf-8'))
                time.sleep(0.05) # 稍微减少等待时间提高响应

                while ser.in_waiting:
                    response = ser.readline().decode('utf-8', errors='ignore').strip()
                    if response:
                        print(f"[ESP32]: {response}")

            except serial.SerialException as e:
                print(f"\n[错误] 串口连接中断: {e}")
                print("请检查电源是否稳定（双舵机耗电更大！）")
                break

    except KeyboardInterrupt:
        print("\n程序中断")
    finally:
        if ser and ser.is_open:
            ser.close()
        print("串口已关闭")

if __name__ == "__main__":
    main()
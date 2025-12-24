import os
from PIL import Image

def crop_transparent_borders(input_dir, output_dir):
    """
    遍历指定文件夹下的所有PNG图片，裁切掉透明边缘，并保存到输出文件夹。
    """
    # 如果输出文件夹不存在，则创建它
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 遍历文件夹
    for filename in os.listdir(input_dir):
        if filename.lower().endswith(".png"):
            img_path = os.path.join(input_dir, filename)

            try:
                with Image.open(img_path) as img:
                    # 确保图片是 RGBA 模式（包含透明通道）
                    img = img.convert("RGBA")

                    # 获取非零区域的边界框 (left, upper, right, lower)
                    # getbbox() 会忽略完全透明的像素
                    bbox = img.getbbox()

                    if bbox:
                        # 进行裁切
                        cropped_img = img.crop(bbox)

                        # 保存裁切后的图片
                        output_path = os.path.join(output_dir, filename)
                        cropped_img.save(output_path)
                        print(f"已处理: {filename} -> 裁切后尺寸: {cropped_img.size}")
                    else:
                        print(f"跳过: {filename} (图片可能完全透明)")

            except Exception as e:
                print(f"处理文件 {filename} 时出错: {e}")

if __name__ == "__main__":
    # 输入文件夹路径
    input_folder = "gesture_images"

    # 输出文件夹路径 (可以是同一个文件夹，但这会覆盖原文件，建议先用新文件夹测试)
    output_folder = "gesture_images_cropped"

    # 检查输入文件夹是否存在
    if os.path.exists(input_folder):
        print(f"开始处理文件夹: {input_folder} ...")
        crop_transparent_borders(input_folder, output_folder)
        print("\n处理完成！")
        print(f"裁切后的图片保存在: {output_folder}")
    else:
        print(f"错误: 找不到文件夹 '{input_folder}'。请确保它在当前脚本目录下。")
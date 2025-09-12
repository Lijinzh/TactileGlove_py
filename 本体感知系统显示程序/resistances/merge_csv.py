#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV文件合并工具
用于合并当前目录及其子目录中的所有CSV文件（不添加额外表头）
"""

import os
import csv
import glob
import pandas as pd
from pathlib import Path
from datetime import datetime
import argparse
import sys

class CSVFileMerger:
    def __init__(self):
        self.merged_count = 0
        self.error_files = []

    def find_csv_files(self, search_pattern="*.csv", recursive=True):
        """
        查找当前目录及其子目录中的所有CSV文件

        Args:
            search_pattern: 文件匹配模式
            recursive: 是否递归搜索子目录

        Returns:
            list: CSV文件路径列表
        """
        csv_files = []

        if recursive:
            # 递归搜索当前目录及其所有子目录中的CSV文件
            for root, dirs, files in os.walk('.'):
                for file in files:
                    if file.endswith('.csv') and glob.fnmatch.fnmatch(file, search_pattern):
                        file_path = os.path.join(root, file)
                        csv_files.append(file_path)
        else:
            # 只在当前目录中搜索
            csv_files = glob.glob(search_pattern)

        return csv_files

    def merge_files_simple(self, output_filename="merged_data.csv", file_pattern="*.csv", recursive=True):
        """
        简单合并模式 - 只合并原始数据，不添加额外表头

        Args:
            output_filename: 输出文件名
            file_pattern: 文件匹配模式
            recursive: 是否递归搜索子目录

        Returns:
            bool: 是否成功
        """
        try:
            print(f"开始搜索匹配模式 '{file_pattern}' 的CSV文件...")
            if recursive:
                print("递归搜索子目录")
            else:
                print("仅在当前目录搜索")

            # 查找CSV文件
            csv_files = self.find_csv_files(file_pattern, recursive)

            if not csv_files:
                print("未找到任何匹配的CSV文件进行合并")
                return False

            print(f"找到 {len(csv_files)} 个CSV文件:")
            for file in csv_files[:15]:  # 只显示前15个文件
                print(f"  - {file}")
            if len(csv_files) > 15:
                print(f"  ... 还有 {len(csv_files) - 15} 个文件")

            # 读取并合并所有CSV文件
            dataframes = []
            headers = None

            for file_path in csv_files:
                try:
                    print(f"正在处理: {file_path}")

                    # 检查文件是否为空
                    if os.path.getsize(file_path) == 0:
                        print(f"警告: 文件 {file_path} 为空，跳过")
                        self.error_files.append((file_path, "文件为空"))
                        continue

                    # 读取CSV文件
                    df = pd.read_csv(file_path)

                    # 检查是否有数据
                    if df.empty:
                        print(f"警告: 文件 {file_path} 没有数据，跳过")
                        self.error_files.append((file_path, "无数据"))
                        continue

                    # 不添加额外的文件来源信息，保持原始数据结构
                    dataframes.append(df)
                    self.merged_count += len(df)

                except Exception as e:
                    print(f"读取文件 {file_path} 时出错: {e}")
                    self.error_files.append((file_path, str(e)))
                    continue

            if not dataframes:
                print("未成功读取任何数据文件")
                return False

            # 检查所有数据框的列是否一致
            print("正在检查数据列一致性...")
            all_columns = set()
            for df in dataframes:
                all_columns.update(df.columns)

            if len(all_columns) > 0:
                print(f"所有文件中包含的列: {sorted(list(all_columns))}")

            # 合并所有数据框
            print("正在合并数据...")
            merged_df = pd.concat(dataframes, ignore_index=True, sort=False)

            # 保存到CSV文件
            merged_df.to_csv(output_filename, index=False, encoding='utf-8')

            print(f"\n合并完成!")
            print(f"- 成功处理文件数: {len(dataframes)}")
            print(f"- 合并数据行数: {len(merged_df)}")
            print(f"- 输出文件: {output_filename}")
            print(f"- 列名: {list(merged_df.columns)}")

            # 显示数据预览
            print(f"\n数据预览 (前5行):")
            print(merged_df.head())

            # 显示错误文件（如果有）
            if self.error_files:
                print(f"\n处理过程中遇到 {len(self.error_files)} 个错误:")
                for file_path, error in self.error_files:
                    print(f"  - {file_path}: {error}")

            return True

        except Exception as e:
            print(f"合并文件时发生错误: {e}")
            return False

    def merge_files_with_validation(self, output_filename="merged_data_validated.csv",
                                    file_pattern="*.csv", recursive=True):
        """
        合并文件并验证数据一致性

        Args:
            output_filename: 输出文件名
            file_pattern: 文件匹配模式
            recursive: 是否递归搜索子目录

        Returns:
            bool: 是否成功
        """
        try:
            print(f"开始验证模式合并，搜索匹配模式 '{file_pattern}' 的CSV文件...")
            if recursive:
                print("递归搜索子目录")
            else:
                print("仅在当前目录搜索")

            # 查找CSV文件
            csv_files = self.find_csv_files(file_pattern, recursive)

            if not csv_files:
                print("未找到任何匹配的CSV文件进行合并")
                return False

            print(f"找到 {len(csv_files)} 个CSV文件")

            # 读取并合并所有CSV文件
            dataframes = []
            expected_columns = None

            for file_path in csv_files:
                try:
                    print(f"正在处理: {file_path}")

                    # 读取CSV文件
                    df = pd.read_csv(file_path)

                    if df.empty:
                        print(f"警告: 文件 {file_path} 没有数据，跳过")
                        self.error_files.append((file_path, "无数据"))
                        continue

                    # 验证列结构一致性
                    if expected_columns is None:
                        expected_columns = list(df.columns)
                        print(f"基准列结构: {expected_columns}")
                    else:
                        current_columns = list(df.columns)
                        if set(current_columns) != set(expected_columns):
                            print(f"警告: 文件 {file_path} 列结构不完全匹配")
                            print(f"  基准: {expected_columns}")
                            print(f"  当前: {current_columns}")

                    # 不添加额外的信息，保持原始数据
                    dataframes.append(df)
                    self.merged_count += len(df)

                except Exception as e:
                    print(f"读取文件 {file_path} 时出错: {e}")
                    self.error_files.append((file_path, str(e)))
                    continue

            if not dataframes:
                print("未成功读取任何数据文件")
                return False

            # 合并所有数据框
            print("正在合并数据...")
            merged_df = pd.concat(dataframes, ignore_index=True, sort=False)

            # 数据验证
            print("正在进行数据验证...")
            self.validate_data(merged_df)

            # 保存到CSV文件
            merged_df.to_csv(output_filename, index=False, encoding='utf-8')

            print(f"\n合并完成!")
            print(f"- 成功处理文件数: {len(dataframes)}")
            print(f"- 合并数据行数: {len(merged_df)}")
            print(f"- 输出文件: {output_filename}")
            print(f"- 列名: {list(merged_df.columns)}")

            # 显示统计数据
            self.print_data_statistics(merged_df)

            # 显示错误文件（如果有）
            if self.error_files:
                print(f"\n处理过程中遇到 {len(self.error_files)} 个错误:")
                for file_path, error in self.error_files:
                    print(f"  - {file_path}: {error}")

            return True

        except Exception as e:
            print(f"合并文件时发生错误: {e}")
            return False

    def merge_files_filter_columns(self, output_filename="merged_filtered_data.csv",
                                   file_pattern="*.csv", column_filter=None, recursive=True):
        """
        合并文件并根据指定列进行过滤

        Args:
            output_filename: 输出文件名
            file_pattern: 文件匹配模式
            column_filter: 要包含的列名列表
            recursive: 是否递归搜索子目录

        Returns:
            bool: 是否成功
        """
        try:
            print(f"开始选择性合并，搜索匹配模式 '{file_pattern}' 的CSV文件...")
            if recursive:
                print("递归搜索子目录")
            else:
                print("仅在当前目录搜索")

            if column_filter:
                print(f"将只保留列: {column_filter}")

            # 查找CSV文件
            csv_files = self.find_csv_files(file_pattern, recursive)

            if not csv_files:
                print("未找到任何匹配的CSV文件进行合并")
                return False

            print(f"找到 {len(csv_files)} 个CSV文件")

            # 读取并合并所有CSV文件
            dataframes = []

            for file_path in csv_files:
                try:
                    print(f"正在处理: {file_path}")

                    # 读取CSV文件
                    df = pd.read_csv(file_path)

                    if df.empty:
                        print(f"警告: 文件 {file_path} 没有数据，跳过")
                        self.error_files.append((file_path, "无数据"))
                        continue

                    # 如果指定了列过滤器，则只保留指定的列
                    if column_filter:
                        available_cols = [col for col in column_filter if col in df.columns]
                        missing_cols = [col for col in column_filter if col not in df.columns]

                        if missing_cols:
                            print(f"警告: 文件 {file_path} 缺少列: {missing_cols}")

                        if available_cols:
                            df = df[available_cols]
                        else:
                            print(f"警告: 文件 {file_path} 没有指定的列，跳过")
                            self.error_files.append((file_path, "缺少指定列"))
                            continue

                    # 不添加额外的信息，保持原始数据
                    dataframes.append(df)
                    self.merged_count += len(df)

                except Exception as e:
                    print(f"读取文件 {file_path} 时出错: {e}")
                    self.error_files.append((file_path, str(e)))
                    continue

            if not dataframes:
                print("未成功读取任何数据文件")
                return False

            # 合并所有数据框
            print("正在合并数据...")
            merged_df = pd.concat(dataframes, ignore_index=True, sort=False)

            # 保存到CSV文件
            merged_df.to_csv(output_filename, index=False, encoding='utf-8')

            print(f"\n合并完成!")
            print(f"- 成功处理文件数: {len(dataframes)}")
            print(f"- 合并数据行数: {len(merged_df)}")
            print(f"- 输出文件: {output_filename}")
            print(f"- 列名: {list(merged_df.columns)}")

            # 显示统计数据
            self.print_data_statistics(merged_df)

            # 显示错误文件（如果有）
            if self.error_files:
                print(f"\n处理过程中遇到 {len(self.error_files)} 个错误:")
                for file_path, error in self.error_files:
                    print(f"  - {file_path}: {error}")

            return True

        except Exception as e:
            print(f"合并文件时发生错误: {e}")
            return False

    def validate_data(self, df):
        """
        验证合并后的数据

        Args:
            df: pandas DataFrame
        """
        try:
            print("数据验证结果:")

            # 检查缺失值
            missing_values = df.isnull().sum()
            if missing_values.sum() > 0:
                print(f"- 发现缺失值:")
                for col, count in missing_values[missing_values > 0].items():
                    print(f"  {col}: {count} 个缺失值")
            else:
                print("- 无缺失值")

            # 检查重复行
            duplicates = df.duplicated().sum()
            if duplicates > 0:
                print(f"- 发现 {duplicates} 个重复行")
            else:
                print("- 无重复行")

            # 检查标签列（如果存在）
            if 'label' in df.columns:
                unique_labels = df['label'].nunique()
                print(f"- label列包含 {unique_labels} 个唯一值")

        except Exception as e:
            print(f"数据验证时出错: {e}")

    def print_data_statistics(self, df):
        """
        打印数据统计信息

        Args:
            df: pandas DataFrame
        """
        try:
            print("\n数据统计:")
            print(f"- 总行数: {len(df)}")
            print(f"- 总列数: {len(df.columns)}")

            # 显示数值列的基本统计
            numeric_columns = df.select_dtypes(include=['number']).columns
            if len(numeric_columns) > 0:
                print(f"- 数值列数: {len(numeric_columns)}")

        except Exception as e:
            print(f"生成统计数据时出错: {e}")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='CSV文件合并工具 (不添加额外表头)')
    parser.add_argument('-o', '--output', default='merged_data.csv',
                        help='输出文件名 (默认: merged_data.csv)')
    parser.add_argument('-p', '--pattern', default='*.csv',
                        help='文件匹配模式 (默认: *.csv)')
    parser.add_argument('-m', '--mode', choices=['simple', 'validate', 'filter'],
                        default='simple', help='合并模式 (默认: simple)')
    parser.add_argument('-c', '--columns', nargs='*',
                        help='filter模式下要包含的列名')
    parser.add_argument('--no-recursive', action='store_true',
                        help='不递归搜索子目录')

    args = parser.parse_args()

    print("CSV文件合并工具 (保持原始数据结构)")
    print("=" * 50)

    # 创建合并器实例
    merger = CSVFileMerger()

    # 确定是否递归搜索
    recursive = not args.no_recursive

    # 根据模式执行合并
    if args.mode == 'simple':
        success = merger.merge_files_simple(args.output, args.pattern, recursive)
    elif args.mode == 'validate':
        success = merger.merge_files_with_validation(args.output, args.pattern, recursive)
    elif args.mode == 'filter':
        success = merger.merge_files_filter_columns(args.output, args.pattern, args.columns, recursive)
    else:
        print("未知的合并模式")
        return 1

    if success:
        print(f"\n程序执行成功!")
        return 0
    else:
        print(f"\n程序执行失败!")
        return 1

if __name__ == "__main__":
    # 如果直接运行脚本，使用命令行参数
    if len(sys.argv) > 1:
        exit_code = main()
        sys.exit(exit_code)
    else:
        # 交互式使用
        print("CSV文件合并工具 (保持原始数据结构)")
        print("=" * 50)
        print("1. 简单合并")
        print("2. 合并并验证数据")
        print("3. 选择性合并（指定列）")

        try:
            choice = input("请选择合并模式 (1-3): ").strip()

            output_file = input("请输入输出文件名 (默认: merged_data.csv): ").strip()
            if not output_file:
                output_file = "merged_data.csv"

            pattern = input("请输入文件匹配模式 (默认: *.csv): ").strip()
            if not pattern:
                pattern = "*.csv"

            recursive_choice = input("是否递归搜索子目录？(y/n, 默认: y): ").strip().lower()
            recursive = recursive_choice != 'n'

            merger = CSVFileMerger()

            if choice == "1":
                merger.merge_files_simple(output_file, pattern, recursive)
            elif choice == "2":
                merger.merge_files_with_validation(output_file, pattern, recursive)
            elif choice == "3":
                columns_input = input("请输入要包含的列名（用空格分隔，直接回车包含所有列）: ").strip()
                columns = columns_input.split() if columns_input else None
                merger.merge_files_filter_columns(output_file, pattern, columns, recursive)
            else:
                print("无效的选择")

        except KeyboardInterrupt:
            print("\n用户取消操作")
        except Exception as e:
            print(f"程序执行出错: {e}")

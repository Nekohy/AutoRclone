# 使用7z官方的二进制文件
import logging
import os
import subprocess
import re
from typing import List, Dict

class FileProcess:
    def __init__(self,compress:str,tmp:str,mmt:int,repack=True,password:str=None):
        # 7z二进制文件
        self.compress = compress
        # 临时转储路径
        self.tmp = tmp
        # 自动删除中间文件
        self.autodelete = True
        # 是否解压后重打包
        self.repack = repack
        # 线程数
        self.mmt = 1 if mmt is None else mmt
        # 是否自动重打包
        if self.repack:
            # 重打包密码
            self.password = password
            # 压缩值（0-9，0为仅储存）
            self.mx = 0

    def decompress(self,src_fs,dst_fs,passwords:list=[None,]):
        """
        解压文件到指定路径
        :param passwords: 可用的密码列表
        :param src_fs: 目标压缩文件所在文件夹
        :param dst_fs: 解压工作路径 例如 “./tmp”
        :return: 解压后文件所在路径
        """
        if not os.path.exists(src_fs):
            logging.error(f"错误：源文件夹 {src_fs} 不存在")

        if not os.path.exists(dst_fs):
            os.makedirs(dst_fs)

        command = [
            '7z',
            'x',
            src_fs,
            f'-o{dst_fs}',
            '-aoa',  #  覆盖文件
            f'-mmt={self.mmt}'  # 可以根据需求调整，或使用 '-mmt=on'
        ]
        for pwd in passwords:
            command = command + [f'-{pwd}'] if pwd else command
            logging.debug(f"当前解压缩命令 {command}")
            try:
                result = subprocess.run(command, capture_output=True, text=True)
                logging.debug(f"当前解压缩日志{result.stdout}")
                if result.returncode == 0:
                    logging.info(f"{src_fs}成功解压到{dst_fs}")
                    return dst_fs
                elif "Wrong password" in result.stderr:
                    logging.warning(f"{src_fs}密码 '{pwd}' 不正确，尝试下一个密码")
                else:
                    logging.error(f"{src_fs}解压过程中发生错误: {result.stderr}")
                    return None
            except Exception as e:
                logging.error(f"{src_fs}解压过程发生未预期的错误: {e}")
                return None
        logging.error(f"{src_fs}没有正确的密码用来解压")
        return None


    def compress(self,src_fs:str,dst_fs:str,password:str=None,mx:int=0):
        pass

    def categorize_archives_grouped(self,file_list: List[Dict]) -> Dict[str, Dict]:
        """
        按基础文件名和Path分类文件，并计算这些文件的总大小。

        Args:
            file_list (List[Dict]): 包含文件信息的字典列表，每个字典包含 'Name' 和 'Path' 键。

        Returns:
            Dict[str, Dict]: 嵌套字典，第一层键为基础文件名，
                             值为包含 'paths' 列表和 'total_size' 的字典。
        """
        # 定义压缩类型及其匹配模式的正则表达式
        patterns = {
            'rar': re.compile(r'^(?P<base>.+?)(?:\.part\d+)?\.rar$', re.IGNORECASE),
            '7z': re.compile(r'^(?P<base>.+?)\.7z(?:\.\d{3})?$', re.IGNORECASE),
            'zip': re.compile(r'^(?P<base>.+?)\.zip(?:\.\d{3})?$', re.IGNORECASE),
            # 仅匹配包含分卷标识的自解压压缩包，如 'filename.part01.exe' 或 'filename.001.exe'
            'sfx': re.compile(r'^(?P<base>.+?)\.(?:part\d+|\d{3})\.exe$', re.IGNORECASE)
        }

        categorized = {}

        for file in file_list:
            name = file.get('Name', '')
            path = file.get('Path', '')
            size = file.get('Size', 0)
            matched = False  # 标记文件是否已被匹配

            for file_type, pattern in patterns.items():
                match = pattern.match(name)
                if match:
                    base_name = match.group('base')
                    if base_name not in categorized:
                        categorized[base_name] = {'paths': set(), 'total_size': 0}
                    categorized[base_name]['paths'].add(path)
                    categorized[base_name]['total_size'] += size
                    matched = True
                    break  # 匹配成功后不再继续检测其他类型

            if not matched:
                # 文件不属于定义的任何压缩类型或 SFX，忽略或根据需要处理
                pass

        # 将路径集合转换为列表，并计算每个基本文件名的总大小
        for base in categorized:
            categorized[base]['paths'] = sorted(categorized[base]['paths'])

        return categorized
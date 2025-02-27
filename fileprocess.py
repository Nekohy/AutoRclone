# 使用7z官方的二进制文件
import concurrent.futures
import os
import shutil
import subprocess
import re
from typing import List, Dict

from Exception import PackError, NoRightPasswd, UnpackError, NoExistDecompressDir


class FileProcess:
    def __init__(self,mmt:int=1,p7zip_file:str="7z",autodelete:bool=True):
        # 7z二进制文件
        self.p7zip_file = p7zip_file
        # 压缩线程默认为1
        self.mmt = mmt
        # 自动删除中间文件
        self.autodelete = autodelete

    # noinspection PyDefaultArgument
    def decompress(self, src_fs, dst_fs, passwords: list = [], max_workers=8):
        """
        解压文件到指定路径
        :param passwords: 可用的密码列表
        :param src_fs: 目标压缩文件所在文件夹
        :param dst_fs: 解压工作路径 例如 "./tmp"
        :param max_workers: 最大线程数量
        :return: 解压后文件所在路径
        """
        passwords.append(None)
        if not os.path.exists(src_fs):
            raise NoExistDecompressDir(f"错误：源文件夹 {src_fs} 不存在")
        os.makedirs(dst_fs, exist_ok=True)

        origin_command = [
            self.p7zip_file,
            'x',
            src_fs,
            f'-o{dst_fs}',
            '-aoa',  # 覆盖文件
            f'-mmt={self.mmt}'
        ]
        if self.autodelete:
            origin_command.append('-sdel')

        def try_decompress(pwd):
            command = origin_command + ([f'-p{pwd}'] if pwd else ['-p'])
            result = subprocess.run(command, capture_output=True, text=True)
            return result, pwd

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_pwd = {executor.submit(try_decompress, pwd): pwd for pwd in passwords}
            for future in concurrent.futures.as_completed(future_to_pwd):
                result, pwd = future.result()
                if result.returncode == 0:
                    executor.shutdown(wait=False, cancel_futures=True)
                    return dst_fs
                elif "Wrong password" in result.stderr:
                    continue
                else:
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise UnpackError(f"{src_fs}解压过程中发生错误: {result.stderr}\n标准输出: {result.stdout}")

        raise NoRightPasswd(f"{src_fs}没有正确的密码")

    def compress(self, src_fs: str, dst_fs: str, password: str = None,mx:int=0,volumes: str = "4G"):
        """
        压缩文件或目录
        :param src_fs: 目标文件夹
        :param dst_fs: 压缩文件输出路径
        :param mx: 压缩率，默认为0，范围0-10
        :param password: 压缩密码，默认为空
        :param volumes: 分卷大小，默认为4g
        :return: 压缩包文件名称
        """

        command = [self.p7zip_file, 'a','-y','-mx' + str(mx).lower(),f'-mmt={self.mmt}']  # 基本命令：添加到压缩包，仅储存，压缩后删除源文件
        if self.autodelete:
            command.append('-sdel')
        # 获取文件名
        src_name = os.path.basename(src_fs.rstrip(os.path.sep))
        dst_location = os.path.join(dst_fs, f"{src_name}.7z")

        # 添加密码（如果提供）
        if password:
            command.extend([f'-p{password}'])

        # 添加分卷设置（如果提供）
        if volumes:
            command.extend([f'-v{volumes}'])

        # 添加输出路径和需要压缩的源路径
        command.extend([dst_location, src_fs])
        # self.logging.debug(f"当前压缩命令 {command}")
        # 执行命令
        result = subprocess.run(command, capture_output=True, text=True)
        # self.logging.debug(f"当前压缩日志{result.stdout}")
        if result.returncode == 0:
            # self.logging.info(f"{src_fs}成功压缩并存放到{dst_fs}")
            return dst_fs
        else:
            raise PackError(f"{src_fs}压缩过程中发生错误: {result.stderr}")

    def filter_files(self, file_list: List[Dict], fs: str = None, depth: int = 0) -> Dict[str, Dict]:
        """
        按基础文件名和路径分类文件，并计算这些文件的总大小。

        Args:
            file_list (List[Dict]): 包含文件信息的字典列表，每个字典包含 'Name' 和 'Path' 键。
            fs: 添加到文件名前的附加路径，例如 Alist:
            depth: 使用路径中的目录作为基础文件名的深度。0 表示使用文件名。

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
        if not file_list:
            raise ValueError("No File List To Filter")

        for file in file_list:
            base_name = file.get('Name', '')
            path = file.get('Path', '').replace('\\', '/')
            size = file.get('Size', 0)
            matched = False  # 标记文件是否已被匹配

            if depth == 0:
                output_name = base_name
            else:
                path_parts = path.split('/')
                if len(path_parts) >= depth or depth < 0:
                    output_name = path_parts[depth-1]
                else:
                    output_name = base_name  # 如果深度超出路径长度，使用文件名

            for file_type, pattern in patterns.items():
                match = pattern.match(base_name)
                if match:
                    if output_name not in categorized:
                        categorized[output_name] = {'paths': set(), 'total_size': size}
                    categorized[output_name]['paths'].add(os.path.join(fs, path).replace('\\', '/'))
                    categorized[output_name]['total_size'] += size
                    matched = True
                    break  # 匹配成功后不再继续检测其他类型

            if not matched:
                # 文件不属于定义的任何压缩类型或 SFX，忽略或根据需要处理
                pass

        # 将路径集合转换为列表，并计算每个基本文件名的总大小
        for base in categorized:
            categorized[base]['paths'] = sorted(categorized[base]['paths'])

        return categorized

    @staticmethod
    def get_free_size(fs):
        """
        :param fs: 本地文件路径
        :return: 剩余空间大小（字节）
        """
        # 如果文件夹不存在则新建
        os.makedirs(fs, exist_ok=True)
        # 获取磁盘使用情况
        total, used, free = shutil.disk_usage(fs)
        return int(free)


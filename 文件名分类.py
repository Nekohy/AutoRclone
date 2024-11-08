import re
from typing import List, Dict


def categorize_archives_grouped(file_list: List[Dict]) -> Dict[str, Dict]:
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


# 示例使用
if __name__ == "__main__":
    # 示例文件列表，包括您提到的文件和其他可能的文件
    files = [
        {"Path": "BPFT2/幽深密室/Deepest.Chamber.Resurrection.v1.075-P2P.7z",
         "Name": "Deepest.Chamber.Resurrection.v1.075-P2P.7z", "Size": 3017080947, "ModTime": "", "IsDir": False},
        {"Path": "BPFT2/幽灵之歌/Ghost.Song.v1.2.1.rar", "Name": "Ghost.Song.v1.2.1.rar", "Size": 1381341174,
         "ModTime": "", "IsDir": False},
        {"Path": "BPFT2/废品场模拟/Junkyard.Simulator.v2.1.5.part1.rar", "Name": "Junkyard.Simulator.v2.1.5.part1.rar",
         "Size": 3221225472, "ModTime": "", "IsDir": False},
        {"Path": "BPFT2/废品场模拟/Junkyard.Simulator.v2.1.5.part2.rar", "Name": "Junkyard.Simulator.v2.1.5.part2.rar",
         "Size": 3221225472, "ModTime": "", "IsDir": False},
        {"Path": "BPFT2/废品场模拟/Junkyard.Simulator.v2.1.5.part3.rar", "Name": "Junkyard.Simulator.v2.1.5.part3.rar",
         "Size": 3221225472, "ModTime": "", "IsDir": False},
        {"Path": "BPFT2/废品场模拟/Junkyard.Simulator.v2.1.5.part4.rar", "Name": "Junkyard.Simulator.v2.1.5.part4.rar",
         "Size": 3221225472, "ModTime": "", "IsDir": False},
        {"Path": "BPFT2/废品场模拟/Junkyard.Simulator.v2.1.5.part5.rar", "Name": "Junkyard.Simulator.v2.1.5.part5.rar",
         "Size": 372598157, "ModTime": "", "IsDir": False},
        {"Path": "apps/yhy/1/OS X Mavericks 10.9 (GM).iso", "Name": "OS X Mavericks 10.9 (GM).iso", "Size": 6041632768,
         "ModTime": "", "IsDir": False},
        {"Path": "apps/yhy/1/dos-03(150224).vhd", "Name": "dos-03(150224).vhd", "Size": 1791424000, "ModTime": "",
         "IsDir": False},
        {"Path": "apps/yhy/1/dos-win2003.vhd", "Name": "dos-win2003.vhd", "Size": 4126140416, "ModTime": "",
         "IsDir": False},
        {"Path": "apps/yhy/1/unlock-all-v120.zip", "Name": "unlock-all-v120.zip", "Size": 4329002, "ModTime": "",
         "IsDir": False},
        {"Path": "image/2023/12/06-1/65701e7f9205b.webp", "Name": "65701e7f9205b.webp", "Size": 288622, "ModTime": "",
         "IsDir": False},
        {"Path": "image/2023/12/06-1/65701e7f94d0e.webp", "Name": "65701e7f94d0e.webp", "Size": 288622, "ModTime": "",
         "IsDir": False},
        {"Path": "image/2023/12/06-1/65701e800b4c9.webp", "Name": "65701e800b4c9.webp", "Size": 244258, "ModTime": "",
         "IsDir": False},
        {"Path": "image/2023/12/06-1/6570835289ee7.webp", "Name": "6570835289ee7.webp", "Size": 78405, "ModTime": "",
         "IsDir": False},
        {"Path": "image/2023/12/07-1/6571270b263e4.webp", "Name": "6571270b263e4.webp", "Size": 178519, "ModTime": "",
         "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part01.rar", "Name": "DIPXIANXZ.part01.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part02.rar", "Name": "DIPXIANXZ.part02.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part03.rar", "Name": "DIPXIANXZ.part03.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part04.rar", "Name": "DIPXIANXZ.part04.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part05.rar", "Name": "DIPXIANXZ.part05.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part06.rar", "Name": "DIPXIANXZ.part06.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part07.rar", "Name": "DIPXIANXZ.part07.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part08.rar", "Name": "DIPXIANXZ.part08.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part09.rar", "Name": "DIPXIANXZ.part09.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part10.rar", "Name": "DIPXIANXZ.part10.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part11.rar", "Name": "DIPXIANXZ.part11.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part12.rar", "Name": "DIPXIANXZ.part12.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part13.rar", "Name": "DIPXIANXZ.part13.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part14.rar", "Name": "DIPXIANXZ.part14.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part15.rar", "Name": "DIPXIANXZ.part15.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part16.rar", "Name": "DIPXIANXZ.part16.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part17.rar", "Name": "DIPXIANXZ.part17.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part18.rar", "Name": "DIPXIANXZ.part18.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part19.rar", "Name": "DIPXIANXZ.part19.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part20.rar", "Name": "DIPXIANXZ.part20.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part21.rar", "Name": "DIPXIANXZ.part21.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part22.rar", "Name": "DIPXIANXZ.part22.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part23.rar", "Name": "DIPXIANXZ.part23.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part24.rar", "Name": "DIPXIANXZ.part24.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part25.rar", "Name": "DIPXIANXZ.part25.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part26.rar", "Name": "DIPXIANXZ.part26.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part27.rar", "Name": "DIPXIANXZ.part27.rar",
         "Size": 4089446400, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/V1.3.55.0全DLC整合版/DIPXIANXZ.part28.rar", "Name": "DIPXIANXZ.part28.rar",
         "Size": 2586535142, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/升级档/Update.Build.14224699-1.4.59.0.rar",
         "Name": "Update.Build.14224699-1.4.59.0.rar", "Size": 380651534, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/升级档/Update.Build.14835813-V1.5.80.0.rar",
         "Name": "Update.Build.14835813-V1.5.80.0.rar", "Size": 407659996, "ModTime": "", "IsDir": False},
        {"Path": "test/圣剑传说/DIPXXZ/升级档/补丁按版本顺序安装即可.txt", "Name": "补丁按版本顺序安装即可.txt",
         "Size": 103, "ModTime": "", "IsDir": False},
        {"Path": "image/2023/12/08-1/6572dd00074e3.webp", "Name": "6572dd00074e3.webp", "Size": 382094, "ModTime": "",
         "IsDir": False},
        {"Path": "image/2023/12/08-1/6572dd494a76b.webp", "Name": "6572dd494a76b.webp", "Size": 554834, "ModTime": "",
         "IsDir": False},
        {"Path": "image/2023/12/08-1/6572ddc550787.webp", "Name": "6572ddc550787.webp", "Size": 440324, "ModTime": "",
         "IsDir": False},
        {"Path": "image/2023/12/08-1/6572e73fa1eab.webp", "Name": "6572e73fa1eab.webp", "Size": 95502, "ModTime": "",
         "IsDir": False},
        {"Path": "image/2023/12/08-1/6572e745d0a16.webp", "Name": "6572e745d0a16.webp", "Size": 245329, "ModTime": "",
         "IsDir": False},
        {"Path": "image/2023/12/08-1/6572e7fd306e7.webp", "Name": "6572e7fd306e7.webp", "Size": 275179, "ModTime": "",
         "IsDir": False},
        {"Path": "image/2023/12/08-1/6572f46c692cc.webp", "Name": "6572f46c692cc.webp", "Size": 667144, "ModTime": "",
         "IsDir": False},
        {"Path": "image/2023/12/08-1/6572f47018851.webp", "Name": "6572f47018851.webp", "Size": 792004, "ModTime": "",
         "IsDir": False},
        {"Path": "image/2023/12/08-1/6572f4f8a7290.webp", "Name": "6572f4f8a7290.webp", "Size": 556579, "ModTime": "",
         "IsDir": False},
        {"Path": "image/2023/12/08-1/65730a14b72b0.webp", "Name": "65730a14b72b0.webp", "Size": 303028, "ModTime": "",
         "IsDir": False},
        {"Path": "image/2023/12/07-3/6571a31c30619.webp", "Name": "6571a31c30619.webp", "Size": 314832, "ModTime": "",
         "IsDir": False},
        {"Path": "image/2023/12/07-3/6571a3d0ceaeb.webp", "Name": "6571a3d0ceaeb.webp", "Size": 165100, "ModTime": "",
         "IsDir": False},
        {"Path": "image/2023/12/07-3/6571a3e606a0c.webp", "Name": "6571a3e606a0c.webp", "Size": 923771, "ModTime": "",
         "IsDir": False},
        {"Path": "image/2023/12/07-3/6571a8ad6050a.webp", "Name": "6571a8ad6050a.webp", "Size": 587940, "ModTime": "",
         "IsDir": False},
        {"Path": "image/2023/12/07-3/6571ab44421f1.webp", "Name": "6571ab44421f1.webp", "Size": 332498, "ModTime": "",
         "IsDir": False}, {"Path": "BPFT2/幽深密室/Deepest.Chamber.v0.88-P2P/Deepest Chamber.part1.exe",
                           "Name": "Deepest Chamber.part1.exe", "Size": 1073741824, "ModTime": "", "IsDir": False},
        {"Path": "BPFT2/幽深密室/Deepest.Chamber.v0.88-P2P/Deepest Chamber.part2.rar",
         "Name": "Deepest Chamber.part2.rar", "Size": 1073741824, "ModTime": "", "IsDir": False},
        {"Path": "BPFT2/幽深密室/Deepest.Chamber.v0.88-P2P/Deepest Chamber.part3.rar",
         "Name": "Deepest Chamber.part3.rar", "Size": 544421150, "ModTime": "", "IsDir": False},
        {"Path": "image/2023/12/18-1/658057d204008.webp", "Name": "658057d204008.webp", "Size": 465946, "ModTime": "",
         "IsDir": False},
        {"Path": "image/2023/12/18-1/65805803d616c.webp", "Name": "65805803d616c.webp", "Size": 23000, "ModTime": "",
         "IsDir": False},
        {"Path": "image/2023/12/18-1/658058042ca1b.webp", "Name": "658058042ca1b.webp", "Size": 27621, "ModTime": "",
         "IsDir": False},
        {"Path": "image/2023/12/18-1/65805804952b2.webp", "Name": "65805804952b2.webp", "Size": 32211, "ModTime": "",
         "IsDir": False},
        {"Path": "BPFT2/废墟骑士/Rune.Knights.Build.9496296/Rune.Knights.Build.9496296.part1.rar",
         "Name": "Rune.Knights.Build.9496296.part1.rar", "Size": 2147483648, "ModTime": "", "IsDir": False},
        {"Path": "BPFT2/废墟骑士/Rune.Knights.Build.9496296/Rune.Knights.Build.9496296.part2.rar",
         "Name": "Rune.Knights.Build.9496296.part2.rar", "Size": 2147483648, "ModTime": "", "IsDir": False},
        {"Path": "BPFT2/废墟骑士/Rune.Knights.Build.9496296/Rune.Knights.Build.9496296.part3.rar",
         "Name": "Rune.Knights.Build.9496296.part3.rar", "Size": 2147483648, "ModTime": "", "IsDir": False},
        {"Path": "BPFT2/废墟骑士/Rune.Knights.Build.9496296/Rune.Knights.Build.9496296.part4.rar",
         "Name": "Rune.Knights.Build.9496296.part4.rar", "Size": 1152939256, "ModTime": "", "IsDir": False},
        {
            "Path": "BPFT2/开罗物语合集10_闪耀滑雪场物语森+丘露营地物语+网球俱乐部物语_STEAM官中-3合1/K10/KAILUO.part01.exe",
            "Name": "KAILUO.part01.exe", "Size": 31457280, "ModTime": "", "IsDir": False},
        {
            "Path": "BPFT2/开罗物语合集10_闪耀滑雪场物语森+丘露营地物语+网球俱乐部物语_STEAM官中-3合1/K10/KAILUO.part02.rar",
            "Name": "KAILUO.part02.rar", "Size": 31457280, "ModTime": "", "IsDir": False},
        {
            "Path": "BPFT2/开罗物语合集10_闪耀滑雪场物语森+丘露营地物语+网球俱乐部物语_STEAM官中-3合1/K10/KAILUO.part03.rar",
            "Name": "KAILUO.part03.rar", "Size": 31457280, "ModTime": "", "IsDir": False},
        {
            "Path": "BPFT2/开罗物语合集10_闪耀滑雪场物语森+丘露营地物语+网球俱乐部物语_STEAM官中-3合1/K10/KAILUO.part04.rar",
            "Name": "KAILUO.part04.rar", "Size": 21722074, "ModTime": "", "IsDir": False},
        {"Path": "BPFT2/开罗物语合集11-开拓神秘岛DX+温泉物语2_官方中文/DXC/XXXXX520.exe", "Name": "XXXXX520.exe",
         "Size": 71776723, "ModTime": "", "IsDir": False},
        {"Path": "BPFT2/异形战机/R Type Final 2 v2 0 3.part1.rar", "Name": "R Type Final 2 v2 0 3.part1.rar",
         "Size": 3984588800, "ModTime": "", "IsDir": False},
        {"Path": "BPFT2/异形战机/R Type Final 2 v2 0 3.part2.rar", "Name": "R Type Final 2 v2 0 3.part2.rar",
         "Size": 3984588800, "ModTime": "", "IsDir": False},
        {"Path": "BPFT2/异形战机/R Type Final 2 v2 0 3.part3.rar", "Name": "R Type Final 2 v2 0 3.part3.rar",
         "Size": 3984588800, "ModTime": "", "IsDir": False},
        {"Path": "BPFT2/异形战机/R Type Final 2 v2 0 3.part4.rar", "Name": "R Type Final 2 v2 0 3.part4.rar",
         "Size": 3984588800, "ModTime": "", "IsDir": False},
        {"Path": "BPFT2/异形战机/R Type Final 2 v2 0 3.part5.rar", "Name": "R Type Final 2 v2 0 3.part5.rar",
         "Size": 1699234664, "ModTime": "", "IsDir": False}
    ]

    categorized_files = categorize_archives_grouped(files)

    # 打印分类结果
    for base, info in categorized_files.items():
        print(f"\n基本文件名: {base}")
        print(f"  Paths:")
        for path in info['paths']:
            print(f"    - {path}")
        print(f"  总大小: {info['total_size']} 字节")

# AutoRclone
一个基于 Rclone 和 7zip 的云存储资源自动化处理工具，如果帮到你了能否给一个Star呢

## 功能特性
- ✨ 支持主流压缩格式（如 7z、zip、rar 等）的分卷和非分卷文件处理
- 🔐 支持自动化处理带密码和无密码的压缩文件
- 📁 支持指定文件夹名，并保留原文件名
- 🚀 基于 Rclone RC HTTP 进行通信
- 💾 使用 SQLite 实现数据存储
- ⚡ 多线程运行，智能调节云端大文件的线程行为
- 🐍 完全基于 Python 标准库构建

## 使用参数
| 参数             | 环境变量         | 默认值            | 说明                                                                                   |
|----------------|--------------|----------------|--------------------------------------------------------------------------------------|
| --rclone       | RCLONE_PATH  | -              | Rclone 可执行文件路径                                                                       |
| --p7zip_file   | P7ZIP_FILE   | -              | 7zip 可执行文件路径                                                                         |
| --src          | SRC          | -              | 源目录路径                                                                                |
| --dst          | DST          | -              | 目标目录路径                                                                               |
| --passwords    | PASSWORDS    | []             | 解压密码列表(多个密码空格分隔)                                                                     |
| --password     | PASSWORD     | -              | 压缩密码                                                                                 |
| --max_threads  | MAX_THREADS  | 2              | 最大并发任务数                                                                              |
| --db_file      | DB_FILE      | ./data.db      | SQLite 数据库路径                                                                         |
| --tmp          | TMP          | ./tmp          | 临时文件目录                                                                               |
| --heart        | HEART        | 10             | Rclone 轮询间隔(秒)                                                                       |
| --mx           | MX           | 0              | 压缩等级(0-9)                                                                            |
| --mmt          | MMT          | 4              | 压缩/解压线程数                                                                             |
| --volumes      | VOLUMES      | 4g             | 分卷大小(支持KB/MB/GB)                                                                     |
| --logfile      | LOGFILE      | AutoRclone.log | 日志文件路径                                                                               |
| --depth        | DEPTH        | 0              | 使用路径中的目录作为最终文件夹名的探测深度,为0则使用文件名，例如 Alist:c/a/b.zip 0使用b为文件名，1使用c,-1使用a，最后输出到dst的该文件夹内 |
| --loglevel     | LOGLEVEL     | INFO           | 日志级别                                                                                 |
| --console_log  | CONSOLE_LOG  | True           | 是否输出控制台日志                                                                            |
| --max_spaces   | MAX_SPACES   | 0              | 脚本允许使用的最大缓存空间，单位字节, 为0为不限制（均预留10%容灾空间）                                               |
| --interface    | INTERFACE    | None           | 指定要监控的网络接口名称，如未指定则监控所有接口的总流量 |

## 参数说明
- 支持命令行参数和环境变量两种配置方式
- 参数优先级: 命令行 > 环境变量 > 默认值
- `passwords` 支持多个密码(环境变量中用空格分隔)
- `volumes` 支持 KB(k)、MB(m)、GB(g) 等单位
- `loglevel` 仅支持: DEBUG/INFO/WARNING/ERROR/CRITICAL

## 待办事项
- [ ] 修复 Linux 环境下系统 Rclone 启动问题
- [ ] 添加 Rclone 鉴权功能
- [ ] 支持多目标上传
- [ ] 进度条显示进度
- [ ] ...

## 依赖
- Python 3.x
- Rclone
- 7zip

## License
MIT
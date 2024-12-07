# AutoRclone
一个基于 Rclone 和 7zip 的云存储资源自动化处理工具。

## 功能特性
- ✨ 支持主流压缩格式(7z/zip/rar等)的分卷/非分卷文件处理
- 🔐 支持带密码/无密码压缩文件的自动化处理
- 📁 保留原始目录结构和文件名
- 🚀 基于 Rclone RC HTTP 通信
- 💾 使用 SQLite 实现数据存储
- 🎯 智能调节云端大文件线程行为

## 使用参数
| 参数            | 环境变量        | 默认值            | 说明               |
|---------------|-------------|----------------|------------------|
| --rclone      | RCLONE_PATH | -              | Rclone 可执行文件路径   |
| --p7zip_file  | P7ZIP_FILE  | -              | 7zip 可执行文件路径     |
| --src         | SRC         | -              | 源目录路径            |
| --dst         | DST         | -              | 目标目录路径           |
| --passwords   | PASSWORDS   | []             | 解压密码列表(多个密码空格分隔) |
| --password    | PASSWORD    | -              | 压缩密码             |
| --max_threads | MAX_THREADS | 2              | 最大并发任务数          |
| --db_file     | DB_FILE     | ./data.db      | SQLite 数据库路径     |
| --tmp         | TMP         | ./tmp          | 临时文件目录           |
| --heart       | HEART       | 10             | Rclone 轮询间隔(秒)   |
| --mx          | MX          | 0              | 压缩等级(0-9)        |
| --mmt         | MMT         | 4              | 压缩/解压线程数         |
| --volumes     | VOLUMES     | 4g             | 分卷大小(支持KB/MB/GB) |
| --logfile     | LOGFILE     | AutoRclone.log | 日志文件路径           |
| --depth       | DEPTH       | 0              | 目录名称探测深度         |
| --loglevel    | LOGLEVEL    | INFO           | 日志级别             |
| --console_log | CONSOLE_LOG | True           | 是否输出控制台日志        |

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
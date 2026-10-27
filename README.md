# 项目工作台

**简体中文** | [English](README.en.md)

一个本地优先的项目管理工作台，提供任务视图、AI 辅助排期和局域网协作。参考[原帖](https://www.xiaohongshu.com/explore/6adca1440000000024035ec5)公开展示的功能独立实现；并非原作者发布的软件，内部规则和功能细节不保证一致。

[下载已发布版本](https://github.com/SvenKunkka/local-project-workspace/releases)

## 使用

Mac：打开 DMG，将“项目工作台”拖入“应用程序”后启动。Windows：解压 Windows 压缩包，运行其中的 `ProjectWorkspace.exe`，需要 Windows 10/11 x64 和 Microsoft Edge WebView2 Runtime。Linux：解压 Linux 压缩包，在图形桌面运行 `ProjectWorkspace/ProjectWorkspace`；构建目标为 Ubuntu 24.04 x86_64，其他发行版需要兼容的 Qt / 图形库。Linux 通知需要 `notify-send` 和可用的桌面通知服务。

Mac 首次请求通知时，请在系统提示中选择是否允许；通知被拒绝时到期提醒会保留，待授权后应用运行时再处理。数据位置：Mac 为 `~/.local/share/local-project-manager/`；Linux 为 `$XDG_DATA_HOME/local-project-manager/`（默认 `~/.local/share/local-project-manager/`）；Windows 为 `%LOCALAPPDATA%\LocalProjectWorkspace\`。数据库升级前自动生成带时间的 SQLite 备份。界面可导出 JSON，导入时创建独立副本，不覆盖现有项目；成员身份和密钥不随副本恢复。

本地任务支持项目、列表、看板拖动排序、标签筛选、甘特图、多个负责人、子任务、计划/实际日期、优先级、逾期标记、任务状态流转和日报周报。AI 助手可连接 OpenAI 兼容接口，建议逐条确认后执行。API 地址需包含版本路径，如本机 Ollama 的 `http://127.0.0.1:11434/v1`；发送时当前筛选内的任务和项目列表会传给模型服务。API 密钥仅留在当前页面内存。总览的流转统计只覆盖升级后记录的状态变化，不推算更早的历史。

## 局域网

默认关闭。主机在“局域网协作”中手动开启，再为成员签发邀请链接。成员可以用浏览器打开，或在桌面应用的“局域网协作 → 加入其他主机”输入链接；返回本机工作区使用应用菜单或协作页按钮。主机、管理员、编辑者、只读成员有不同权限。主机关闭应用后共享结束，下次启动需重新开启。断线后当前页面保留已加载内容、禁止修改，并自动重试。

局域网使用未加密 HTTP，链接是可重复使用的身份凭证。仅在可信局域网内使用并私下发送链接；主机可撤销身份。编辑锁会在 120 秒失联后过期。已进行一次跨设备连接与任务修改测试；复杂并发和安全审计尚未完成，暂不适合存放敏感数据。

## 提醒和限制

支持到点一次、提前 30 分钟及到点、每天重复提醒。桌面应用需保持运行并获通知授权；应用关闭或电脑休眠期间不会准时提醒，重新运行后才处理到期提醒。成员使用桌面应用加入主机后，收到负责人字段中与其成员名一致的任务提醒；多人姓名使用逗号分隔。Windows 使用系统 PowerShell 发送通知，Linux 使用 `notify-send`；成功提交给系统不保证系统会显示。浏览器访问不能提供系统通知。日报周报根据当前任务和更新记录整理，非完整历史审计。

Mac 应用使用临时本地签名，未使用 Apple 开发者证书签名或公证，其他 Mac 可能阻止打开；当前构建仅针对 Apple Silicon 且最低要求 macOS 26。Windows 包未经代码签名，可能触发 SmartScreen。由于测试机器的通知权限关闭，尚未完成真实系统通知弹出验证。

## 从源码运行和测试

需要 Python 3。浏览器版本可在项目目录运行 `python3 server.py`，然后访问 `http://127.0.0.1:8765`。退出进程会停止服务。运行 `python3 test_integration.py` 可使用临时数据库执行接口测试。

Mac 应用外壳源码为 `MacApp.m`，可使用 macOS 命令行开发工具和 PyInstaller 构建。Windows / Linux 外壳为 `desktop.py`，分别安装 `pywebview` 和 `pywebview[qt]`，再运行 `python -m PyInstaller desktop.spec`。构建时还需安装 `pyinstaller` 和 `certifi`。运行 `python test_desktop.py` 验证桌面桥接和提醒确认逻辑。构建产物不包含在源码仓库中。

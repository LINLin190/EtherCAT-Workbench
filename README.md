# EtherCAT Workbench

面向 Windows 的 EtherCAT 从站调试与诊断工作台。

桌面端使用 **Tauri 2 + React + TypeScript + Material UI + Emotion**。Python 只负责 EtherCAT 硬件核心，通过常驻本地桥接进程与 Tauri 通信；浏览器层不直接访问 pySOEM。

## 功能

- 用户显式检测网卡、连接和扫描；扫描成功后保持连接
- INIT / PRE-OP / SAFE-OP / OP 状态控制与故障恢复
- ESC 标准寄存器搜索、读取、监视和两阶段安全写入
- ESI XML 自动生成 SII、Smart View、容量检查、完整读取、BIN 备份、烧录、验证与恢复
- 当前界面聚焦概览、寄存器和 EEPROM；CoE、PDO 映射与在线 I/O 暂时隐藏
- 概览页从站右键菜单可快速进入对应 EEPROM 烧录页面；浏览器默认右键菜单已禁用
- 设置包含通用选项和关于信息，可查看版本、许可证并访问 GitHub 项目与问题反馈
- Real 和 Demo 两种后端；Real 为默认模式，Demo 仅从设置启用并持续显示标识

## 架构

```text
React + Material UI + Emotion
              │
              ▼
        Tauri 2 / Rust
              │ 私有 Named Pipe 分帧 JSON
              ▼
       Python Bridge
              │
              ▼
EtherCatWorker → Services → Real/Mock Backend → pySOEM
```

同一个 EtherCAT Master 的请求全部由唯一 Worker 串行执行。EEPROM、寄存器和 PDO 写入的状态检查、确认与验证保留在 Python 服务层，不依赖页面状态保证安全。

## 开发环境

- Windows 10/11 x64
- Node.js 20+ 与 pnpm
- Rust MSVC 工具链
- Python 3.11+
- Windows WebView2
- Real 模式：`pysoem==1.1.13` 与启用 WinPcap API-compatible Mode 的 Npcap

```powershell
python -m pip install -e ".[dev]"
Set-Location desktop
pnpm install
Set-Location ..
.\start-desktop.ps1
```

也可以直接双击项目根目录的 `Start-EtherCAT-Workbench.cmd`。启动器会优先使用已安装的
`pnpm`，找不到时先使用 Corepack 已缓存的兼容版本，仍不可用时再由 Corepack 获取项目指定版本；
首次启动会自动安装前端依赖。

只运行浏览器布局预览：

```powershell
Set-Location desktop
pnpm dev
```

浏览器预览使用内置 Demo 数据，不访问真实网卡。

## 验证

```powershell
python -m ruff check src tests
python -m pytest -q
Set-Location desktop
pnpm build
```

主要设计分辨率为 `2560 × 1440` 和 `1920 × 1080`，兼容下限为 `1280 × 720`。

## 安全说明

PDO 输出、ESC 寄存器和 EEPROM 写入可能立即影响设备。Real 模式下应使用独立网卡和隔离测试环境，在写入前核对从站、地址与目标文件，并确保机械设备处于安全状态。

项目不包含或分发 Npcap 安装程序。许可证见 [LICENSE.md](LICENSE.md)，第三方组件声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

# EtherCAT Workbench

面向 Windows 的 EtherCAT 从站调试与诊断工作台。

桌面端使用 **Tauri 2 + Rust + React + TypeScript + Material UI + Emotion**。Python 只负责 EtherCAT 硬件核心，通过常驻本地 JSON 桥接进程与 Tauri 通信；WebView 不直接访问 pySOEM。

[English](README.en.md)

> [!WARNING]
> 应用默认选择 **Real** 模式，但启动后不会自动打开网卡、连接、扫描总线或写入硬件。Real 模式下的状态切换、寄存器写入、周期 I/O 和 EEPROM 操作可能使从站暂时掉线或影响设备。请在隔离、可恢复的测试环境中从只读操作开始。

## 为什么使用 EtherCAT Workbench

EtherCAT Workbench 将总线发现、状态诊断、ESC 寄存器检查和 EEPROM 维护集中在一个桌面工作流中，并把硬件请求隔离到唯一的通信 Worker：

| 关注点 | 实现方式 |
| --- | --- |
| 上手安全 | Real 不自动连接；Demo/Mock 仅在设置中启用，并持续显示 Demo 标识 |
| GUI 响应 | WebView 不调用 pySOEM，硬件操作由 Python Bridge 异步执行 |
| 请求一致性 | 同一 Master 的请求由唯一 Worker 串行调度 |
| 写入控制 | 寄存器使用两阶段计划和回读验证；EEPROM 使用容量、结构、语义和完整回读校验 |
| 无硬件开发 | Mock Backend、Demo 数据和自动化测试无需 EtherCAT 设备 |
| 可追踪性 | UI 进度、JSONL 日志和 `AUDIT` 写入记录保留诊断上下文 |

底层 EtherCAT 主站通信使用 [pySOEM](https://github.com/bnjmnp/pysoem)。Windows Real 模式依赖 [Npcap](https://npcap.com/)；本仓库和应用均不包含或再分发 Npcap。

## 功能概览

| 模块 | 当前能力 |
| --- | --- |
| 总线与状态 | 网卡检测与选择、手动连接/断开、总线扫描、从站身份、AL 状态、INIT/PRE-OP/SAFE-OP/OP 请求、重配置和故障恢复 |
| ESC 寄存器 | ET1100、LAN9252、LAN9253 目录，搜索、分类、位字段、原始地址读取/写入、固定监视、变化高亮和复制 |
| 寄存器写入 | 60 秒写入计划、从站身份绑定、语义化回读验证和 `AUDIT` 审计；原始地址写入要求 HEX 长度与宽度一致 |
| ESI / SII | XML 选择、拖放、最近五条文件、多个 Device 选择、SII 生成、Smart View（类别/偏移/长度/内容预览）和容量检查 |
| EEPROM | 完整读取、BIN 备份、差异 Word 写入、逐 Word 回读、稳定等待、完整回读、逐字节/SHA-256/结构/身份语义校验、烧录和 BIN 恢复 |
| 复位与重发现 | `0x0040` 的三帧 ESC ECAT reset；复位后在有界时间内轮询重发现，并分别报告重新发现和重新加载复核 |
| 状态诊断 | 概览显示总线阶段、最近通信错误、从站实际状态和 AL 状态码；设置可切换 AL 状态码中文/English |
| 页面范围 | 当前主导航公开概览、寄存器、EEPROM 和设置；CoE、PDO 映射、在线 I/O 页面代码仍保留但暂时隐藏 |

## 架构

```text
React + Material UI + Emotion
              |
              v
        Tauri 2 / Rust
              | persistent JSON channel
              v
       Python Bridge
              |
              v
EtherCatWorker -> Services -> Real/Mock Backend -> pySOEM
```

同一个 EtherCAT Master 的请求全部由唯一 Worker 串行执行。状态检查、确认和验证保留在 Python 服务层，不依赖页面状态保证安全。EEPROM 烧录/恢复期间，其他硬件命令立即返回 `EEPROM_BUSY`；周期通信运行时，状态切换、重配置、故障恢复和 EEPROM 操作会被禁用或拒绝。`recover()` 返回成功后还会复核实际状态和 AL 状态。

## 使用者指南

### 系统与 Npcap 要求

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 10/11 x64 |
| Node.js | 20 或更新版本，以及 pnpm 或 Corepack |
| Python | 3.11 或更新版本 |
| Rust | MSVC 工具链 |
| WebView | Windows WebView2 |
| pySOEM | Real 模式固定使用 `pysoem==1.1.13` |
| Npcap | Real 模式需要 Npcap 1.88+，并启用 **WinPcap API-compatible Mode** |
| 网卡 | 建议使用不承载普通网络业务的独立 EtherCAT 网卡 |

Npcap 不包含在仓库或应用中。Demo 模式不打开真实网卡；Real 模式下若 Npcap/wpcap、权限或网卡不可用，应用会在界面显示错误。

### 安装与启动

当前项目以源码启动为主，Tauri 配置 `bundle.active=false`，不保证存在安装器或 GitHub Release 产物。PowerShell 中执行：

```powershell
git clone https://github.com/LINLin190/EtherCAT-Workbench.git
Set-Location "EtherCAT-Workbench\apps\EtherCAT Workbench"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
.\start-desktop.ps1
```

也可以双击 `Start-EtherCAT-Workbench.cmd`。启动器会优先使用全局 pnpm、本机缓存的 Corepack 版本或 Corepack，并在启动前只清理本项目自有的 Vite 残留进程。Vite 使用 `1420` 端口；若该端口被无关进程占用，脚本会报告冲突并保留该进程。

只运行浏览器布局预览时：

```powershell
Set-Location desktop
pnpm install
pnpm dev
```

浏览器预览使用 Mock 数据，不访问真实网卡。

### 界面与推荐流程

当前公开工作流为：

```text
1. 检测网卡 -> 2. 连接 -> 3. 扫描 -> 4. 选择从站
-> 5. 读取状态和 AL -> 6. 寄存器或 EEPROM 诊断
```

| 页面 | 用途 |
| --- | --- |
| 概览 | 总线阶段、从站身份、实际状态、AL 状态码、状态请求、重配置和故障恢复 |
| 寄存器 | 标准目录、搜索/分类、读取、固定监视、原始地址工具和两阶段写入 |
| EEPROM | ESI/Device 目标、Smart View、容量、读取、BIN 备份、烧录、校验和恢复 |
| 设置 | Real/Demo 模式、AL 状态码语言（中文/English）和关于信息 |

建议顺序：

1. 启动后确认顶部为未连接；Real 模式下检测并选择 EtherCAT 网卡。
2. 点击“连接”，再点击“扫描”，在从站树中选择目标。
3. 先读取概览状态和 AL 状态，按设备要求逐级请求 `INIT -> PRE-OP -> SAFE-OP -> OP`。周期通信运行时不能切换状态。
4. 寄存器先读后写，核对从站、目录、地址、当前值和目标值。写入计划超过 60 秒后必须重新生成。
5. EEPROM 操作前停止周期通信并将目标切换到 INIT。建议先备份 BIN，再选择 XML/Device、检查 Smart View 和容量，最后烧录或恢复。

## AL 状态码

概览页读取 ESC 标准 AL 状态寄存器 `0x0134`，显示代码、名称、详细说明和排查建议。“设置 -> AL 状态码语言”可在中文和 English 间切换，选择保存在本地存储中。

| 范围/代码 | 含义 |
| --- | --- |
| `0x0000` | 无错误 |
| `0x0001`-`0x0083`、`0x00F0`（部分值保留） | 内置通用目录，覆盖固件/SII、状态切换、邮箱、SyncManager、PDO、看门狗、同步、DC、电源、温度和应用控制器条件 |
| `0x8000`-`0xFFFF` | 厂商自定义；界面不会猜测含义，应查阅设备手册、ESI 和厂商诊断对象 |
| 其他值 | 未收录、保留或较新的扩展；应重新读取 `0x0134` 并结合设备资料确认 |

常见诊断方向：

| 类别 | 代码示例 | 首要检查 |
| --- | --- | --- |
| 状态/配置 | `0x0011`、`0x0016`、`0x0017`、`0x0021`-`0x0026` | 当前/目标状态、邮箱、SyncManager、RxPDO/TxPDO、ESI/SII |
| 看门狗/同步 | `0x001A`、`0x001B`、`0x002A`、`0x002C`-`0x0037` | 周期、WKC、Sync0/Sync1、DC 和固件任务负载 |
| 邮箱 | `0x0041`-`0x0045`、`0x004F` | 协议、邮箱长度、对象字典和诊断日志 |
| EEPROM | `0x0050`、`0x0051` | EEPROM 控制/状态/错误寄存器和 SII 镜像 |
| 电源/环境 | `0x0080`-`0x0083` | 供电、散热、环境和外部硬件就绪信号 |

完整的中英文代码、详情和动作建议见 [al_status_codes.json](src/ethercat_debug_tool/protocol/al_status_codes.json) 及前端英文映射。

### `0x0050` EEPROM no access

`0x0050` 表示 **EEPROM 无访问权**：SII EEPROM 未分配给 PDI，或从站固件无法取得所需访问权。该码不能单独证明 PDI 已接管或 EEPROM 被锁定；`0x0500 == 0` 也不是肯定证据。应联合读取 `0x0500`、`0x0501`、`0x0502`，检查 ECAT/PDI 归属、Busy/错误位，并结合固件状态机、日志和抓包判断。`0x0051` 更偏向 EEPROM 读写、应答或校验失败。

状态切换失败时，后端会把从站名、实际状态和 `0x0134` 码带入错误信息。真实设备的 INIT -> PRE-OP 失败仍需硬件、固件和 PDI 路径验证，Demo 测试不能替代真机结论。

## 写入安全机制

### ESC 寄存器

- 默认只读，写入必须经过生成计划和二次确认；计划绑定当前会话、从站完整身份和配置地址，60 秒后失效。
- 写入前重新读取当前值，显示目标从站、地址、当前值、目标值、变化掩码和最终字节。
- RW、W1C、W1S、WO、自清零和易变寄存器使用相应的语义化验证；未知原始地址会明确提示无法判断位语义和副作用。
- 原始地址工具的宽度同时约束读取长度和写入 HEX 字节数，长度不一致会被拒绝；所有写入进入 `AUDIT` 日志。
- LAN9252 兼容档案不会把错误计数器 `0x0300` 当作通用 WAC 直接写入。若要清零，应使用专用且安全的清零操作。
- `0x0040` ESC ECAT reset 使用显式确认的三帧独占序列：`0x52`、`0x45`、`0x53`。

### EEPROM 工作流

> [!WARNING]
> EEPROM 写入只能在周期通信停止且目标从站处于 INIT 时发起。任何一个回读字节、SHA-256、结构或 XML 身份语义校验不一致，都不会显示镜像校验成功。

```text
选择 XML / Device -> 生成完整 SII 目标 -> 检查容量和 Smart View
-> 备份或读取当前 EEPROM -> 仅写入差异 Word -> 逐 Word 回读
-> 稳定等待 -> 完整回读 -> 字节/SHA-256/结构/语义校验
-> 可选 ESC 复位 -> 有界轮询重发现 -> 重新加载复核
```

关键规则：

- 目标镜像完全由用户选择的 XML/Device 或 BIN 生成；不会把 XML 文本直接写入 EEPROM，也不会静默合并旧镜像的序列号、Station Alias 或私有数据。
- Vendor ID、Product Code、Revision 不匹配只显示警告，不强制额外确认，也不单独阻止烧录；操作者必须自行核对目标。
- XML 无法解析、SII 无法生成、物理容量不可读或不匹配、周期通信运行、目标不在 INIT、已有 EEPROM 操作或通信失败时，后端拒绝操作。
- EEPROM 烧录/恢复期间其他硬件命令立即返回 `EEPROM_BUSY`，避免长操作占满 Host deadline 后进程被终止。
- 取消在界面显示为中性的“已取消”，不等同于通信失败；技术详情显示 `first_difference` 首个差异偏移，备份完成后显示完整保存路径。
- 复位后重新发现和重新加载复核分别报告；未重新发现不改变已经完成的镜像字节校验结果。

### ESI -> SII 转换边界

| 状态 | 元素 |
| --- | --- |
| 已支持 | ConfigData/CRC-8、Identity、标准 Mailbox、Strings、General、FMMU、SyncManager、RxPDO/TxPDO、DC OpMode、标准基础 CoE 类型、BIT1-BIT8 |
| 未声称支持 | 厂商私有 Category、完整自定义 DataTypes 字典、EoE/FoE 专属数据、任意 ESI Schema 全覆盖 |

未支持内容会出现在生成报告和 UI 限制说明中，不会被静默忽略。Smart View 显示类别名称、类型、偏移、长度和内容预览。

## ESC Profile 与芯片识别

`chip_model` 与 `register_family` 分开保存。当前档案包括 E101、E252、E253、ET1100、LAN9252、LAN9253 和 Generic ESC；国产型号不会被显示成原厂芯片。识别依据 ESI 型号文字或芯片类型寄存器 `0x0E00`，不会仅凭 FMMU/SM 数量或 RAM 范围猜测。

E101/E252/E253 的厂商私有寄存器、准确 `0x0E00` 编码、EEPROM 时序和复位兼容性尚未通过真机验证；Beckhoff 或其他厂商的 ESC 识别也应以真实硬件和资料复核。

## 开发者指南

### 架构原则

- React 页面负责展示和交互，Tauri Rust 负责桌面生命周期与桥接；
- Python Bridge 是硬件核心的唯一入口，WebView 不直接调用 pySOEM；
- EtherCatWorker 是 Backend 的唯一所有者，同一 Master 的硬件请求串行执行；
- Mock 与 Real Backend 遵循相同接口，Mock 不伪造真实硬件验证结果；
- EEPROM、寄存器和状态操作的条件检查与验证在服务层执行，周期通信和 EEPROM 独占由后端强制约束。

### 日志与数据位置

| 内容 | 位置 |
| --- | --- |
| UI 日志与进度 | 应用窗口内 |
| Bridge JSONL 日志 | `%LOCALAPPDATA%\EtherCATWorkbench\logs` |
| 写入审计 | 同一日志目录，记录为 `AUDIT` |
| EEPROM BIN 备份 | 备份完成后在 EEPROM 页面显示完整路径 |
| Bridge 异常退出 | 页面显示 stderr 和 `log_path`，可直接打开日志位置 |

### 测试与构建检查

全部自动化测试使用 Mock Backend 和随附 ESI/BIN 夹具，不连接真实网卡，也不写真实 PDO 输出、EEPROM 或寄存器：

```powershell
python -m ruff check src tests
python -m pytest -q
Set-Location desktop
pnpm build       # TypeScript 检查 + Vite 构建
pnpm test        # Vitest
```

当前视觉验收基准为 `2560 x 1440`（默认）、`1920 x 1080` 和 `1280 x 720`（最低窗口尺寸）。

## 当前限制与真实硬件验证状态

> [!CAUTION]
> Mock 测试通过不等于真实 EtherCAT 硬件验证通过。

- Npcap 打开、真实状态切换、EEPROM 时序、复杂拓扑复位后的重发现仍需要隔离测试设备；
- INIT -> PRE-OP 的 `0x0050`/`0x0051` 具体固件/PDI 处理路径需要设备资料或抓包；
- E101/E252/E253 的厂商位域、私有寄存器和准确芯片编码需要数据手册或硬件捕获；
- 厂商私有 SII Category 和任意完整 ESI Schema 转换不在当前支持范围；
- 标准公共寄存器目录不代表覆盖每个厂商扩展；
- CoE、PDO 映射和在线 I/O 页面当前隐藏，相关后端能力不属于本版本公开操作承诺。

首次接触真机建议只执行：枚举网卡 -> 连接 -> 扫描 -> 读取状态/AL -> 读取寄存器 -> 读取并离线保存 EEPROM BIN。确认备份可解析且设备处于安全状态后，再在隔离测试从站上验证写入。

## 许可证与贡献

本项目使用 [PolyForm Noncommercial License 1.0.0](LICENSE.md)，属于 source-available 软件，不是 OSI 定义的开源软件。个人、教育、研究及其他非商业用途可按许可证使用、修改和分发；商业产品、收费服务、商业内部运营和付费支持需获得版权所有者另行书面许可。分发时请保留完整许可证、Required Notice、版权声明、项目链接，并明确标注修改内容。第三方组件遵循各自许可证，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

欢迎通过 [GitHub Issues](https://github.com/LINLin190/EtherCAT-Workbench/issues) 报告问题、提出建议或补充经过标注的真机只读验证结果。请提供复现步骤、期望/实际行为、从站与 ESC 型号、ESI 文件、系统环境和验证方式；不要提交会自动写入真实 EEPROM、PDO 输出或寄存器的测试，也不要公开设备序列号、生产配置或私有 ESI。

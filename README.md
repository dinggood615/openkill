<h1 align="center">
  <img src="https://raw.githubusercontent.com/dinggood615/openkill/master/img/logo.png" alt="OpenKill" width="200">
  <br>OpenKill<br>
</h1>

OpenKill 是基于 OpenClash 源码的 OpenWrt 客户端项目。

当前版本：`2026-1040`。

许可：本项目遵循 [MIT License](LICENSE)，并保留上游 OpenClash 及相关组件的版权声明。

安装、更新、卸载统一使用下面这一条指令；不带参数时会显示菜单：

```sh
# 菜单模式：选择安装、更新或卸载
curl -fsSL https://raw.githubusercontent.com/dinggood615/openkill/master/scripts/install-openkill.sh | sh

# 自动化模式：同一入口追加操作参数
curl -fsSL https://raw.githubusercontent.com/dinggood615/openkill/master/scripts/install-openkill.sh | sh -s -- --install   # 安装/修复
curl -fsSL https://raw.githubusercontent.com/dinggood615/openkill/master/scripts/install-openkill.sh | sh -s -- --update    # 更新软件包和内核
curl -fsSL https://raw.githubusercontent.com/dinggood615/openkill/master/scripts/install-openkill.sh | sh -s -- --uninstall  # 卸载并清理

```

更新统一使用 `--update`，会更新 OpenKill 软件包并安装/更新官方稳定 Meta（Mihomo）内核。

IPK/APK 构建完成后独立发布，互不等待。安装器读取对应格式的最新发布清单，优先查询官方仓库，网络失败时回退镜像；下载 Release 附件或镜像副本后校验 SHA256。页面源码版本可能领先于尚在构建的软件包，安装器显示实际选中的发布版本。
项目版本使用 `2026-1040` 形式；后续发布按同一数字序号递增，APK 内部版本转换为 `2026.1040`，以满足 APK 包管理器的版本语法，数字序号保持同步。
依赖索引和安装共用临时源配置；官方 OpenWrt 源不可用时自动尝试北大、清华镜像，保留固件路径和自定义源，不永久修改系统源。依赖下载失败也会重试兼容镜像，必需依赖缺失会停止安装并显示原因。

当前版本已按四阶段基线整理：

1. 配置预检、健康检查、最近可用配置回滚，以及只观察 procd 的 watchdog 防重复重启。
2. 拆分低频维护任务，移除 Smart/LightGBM 运行入口，关闭逐连接进程扫描，降低后台开销。
3. 双栈 DNS/IPv6、Geo 数据和代理组测速采用有界超时与失败重试，减少首连等待和节点抖动。
4. 通过官方 Mihomo stable release 动态获取内核，静态检查脚本与版本清单统一；新增能力探测和可选开关，按内核支持情况启用 ShadowQUIC/QUIC v2、MASQUE 高级参数、AmneziaWG、AnyTLS 元数据、BBR3 与原生 ZeroTier 节点。系统 ZeroTier 服务仍为独立可选项，不作为硬依赖。详见 [Mihomo 兼容基线](docs/MIHOMO_COMPATIBILITY.md)。

2026-1040：第四阶段能力真正接入；新增内核能力探测、ShadowQUIC/QUIC v2、H2C、MASQUE 高级参数、AmneziaWG、AnyTLS 元数据、BBR3 及 ZeroTier 可选开关，并完成节点 UCI/YAML 读写。

2026-1032：修复依赖源重复声明和旧备份缺少路由集合文件的问题；依赖、软件包和官方内核下载增加快速失败与镜像回退，已安装依赖时跳过无必要的源刷新。
2026-1033：修复启动前 Mihomo 配置预检未继承 SAFE_PATHS，导致 external-ui 路径被拒绝、OpenKill 无法启动的问题；统一预检、订阅校验和运行时的安全路径。
2026-1031：按四阶段基线更新 UI；状态页显示官方内核、IPv6/DNS 与 watchdog 配置摘要，版本页改为自动匹配官方 Mihomo 稳定内核，并移除已停用的使用帮助浮层。
2026-1030：完成四阶段稳定性、轻量化、双栈 DNS/测速和官方 Mihomo 兼容基线；新增配置预检/回滚、独立 watchdog 任务与 CI 静态检查。
2026-1020：隔离旧版本缓存，避免升级后继续显示上游 OpenClash 版本列表。
2026-1019：修复版本更新列表仍读取上游 OpenClash 版本的问题，改为读取 OpenKill 自有仓库。
2026-1018：移除运行状态页公告栏并收紧布局间距，减少页面空白和无用请求。
2026-1017：缓存内核版本查询并降低状态页轮询频率，减少 LuCI 与内核短时 CPU 开销。

# OpenKill

OpenKill 是面向 OpenWrt 的轻量化 Mihomo（Meta）客户端 LuCI 插件，基于 OpenClash 兼容架构重构，提供稳定的代理接管、规则分流、双栈 DNS/IPv6 与可回滚运行管理。

当前版本：`2026-2011`

## 一键安装

每条命令都是独立的一行，可直接复制。第一条命令会打开一键操作菜单，可选择安装、更新
或卸载；也可以直接执行下面对应的操作命令。安装器会从最新正式版下载并校验 SHA256。

选择操作（安装、更新或卸载）：

```sh
curl -fsSL https://raw.githubusercontent.com/dinggood615/openkill/master/i | sh
```

直接安装或修复：

```sh
curl -fsSL https://raw.githubusercontent.com/dinggood615/openkill/master/i | sh -s -- --install
```

直接更新软件包和内核：

```sh
curl -fsSL https://raw.githubusercontent.com/dinggood615/openkill/master/i | sh -s -- --update
```

直接卸载并清理 OpenKill 数据：

```sh
curl -fsSL https://raw.githubusercontent.com/dinggood615/openkill/master/i | sh -s -- --uninstall
```

安装器会自动识别 `opkg`/`apk`、设备架构、依赖和可用镜像，并校验软件包 SHA256。更新会保留用户配置和上一份可用内核；卸载只移除 OpenKill 数据，不删除共享依赖。独立 NaiveProxy 组件、Geo 数据和官方 Mihomo/Meta 内核会分别校验，失败时单独报告。

全新安装使用 `performance-dual-stack` 初始配置：IPv4/IPv6 开启、`fake-ip-tun`、
Mihomo `mips` 双栈、BBR3、TCP 并发、统一延迟、标准 Geo、增强广告规则和防火墙 DNS
转发。该配置只包含设备无关的通用设置，不包含节点、订阅、密码、用户 YAML、设备地址
或个人规则；升级和重装保留用户已有选择。

## 功能

- Mihomo/Meta 官方稳定内核兼容：自动识别架构、校验版本与可执行文件，支持 TUN、规则和全局代理模式。
- 稳定启动链路：配置语义预检、原子替换、最近可用配置回滚、控制器/TUN/DNS/防火墙健康检查和有限次恢复。
- 轻量 watchdog：只观察 OpenKill 与 procd 状态，低频维护规则、历史和节点资源；配置采用低频刷新，流媒体自动选择按配置间隔调度，关闭时不再派生后台任务，避免重复拉起核心。
- 高效双栈网络：DNS、IPv6、Geo 数据、代理组测速使用有界超时和失败重试；稳定兼容模式绑定物理 WAN，避免 OpenVPN/PPPoE 重连后 DNS 误绑虚拟接口。
- 三档互斥运行策略：稳定兼容、高性能双栈、Mihomo 原生接管；高性能档启用 TCP 并发、统一延迟和标准 Geo 数据加载，原生档才启用 Mihomo `auto-route`/`auto-redirect`。
- 流量接管互斥：统一管理 TUN、路由和防火墙；OpenKill 接管与 Mihomo 原生自动接管不能同时启用，可在界面切换。
- 原生接管安全切换：切换到 Mihomo `auto-route`/`auto-redirect` 前先清理 OpenKill 规则，校验 fw4 语义检查、真实重载和 nft 表状态；不满足条件时自动回退并记录原因，运行状态会显示“稳定兼容（原生回退）”。
- 规则与订阅管理：支持 GeoIP/GeoSite、大陆白名单、代理组分流、订阅更新、配置检查和安全回滚。
- 可选协议能力：按内核能力探测启用 H2C/ShadowQUIC、QUIC v2、MASQUE、AmneziaWG、AnyTLS、BBR3 和 ZeroTier 相关字段。
- LuCI 界面：运行状态页显示当前接管策略；设置页提供运行与服务、网络与分流、NaiveProxy 与服务、规则与订阅、性能与稳定、兼容设置、系统维护分类；OpenKill 页面继承当前 LuCI 主题的深浅色语义，并提供有界的浅色/深色回退、统一间距和低干扰状态提示。
- 轻量资源策略：基础包只内置 MetaCubeXD；Zashboard、Yacd 和其他面板保留为按需下载，避免首次安装携带重复前端资源。
- 构建清理：安装包不再携带已移除的 OixCloud 页面样式和旧 Smart/LGBM 覆写入口，减少无效资源与配置分支。
- 兼容迁移：旧配置中的 Smart/LightGBM 策略组会自动转换为 Mihomo 原生 `url-test`，废弃的 Smart、LightGBM 与云端凭据字段只执行一次清理，不影响现有订阅节点。
- [兼容设置与 VPN / 远程访问操作指南](docs/VPN_REMOTE_ACCESS.md)：集中管理服务端口绕过、目标地址/端口绕过和旁路由兼容；不改变 VPN 客户端的公网分流策略。
- 故障保护：缺少路由集合文件时自动创建兼容空集合，健康检查失败不覆盖上一份有效配置，日志记录每个安装与启动阶段。

## 兼容性

适用于带 `opkg` 或 `apk` 的 OpenWrt 固件。软件包与内核按设备架构和包管理器自动选择；厂商自带源保持原 ABI，标准 OpenWrt 源才会使用镜像回退。真实吞吐取决于固件、线路、节点和硬件能力。

## 许可

本项目遵循 [MIT License](LICENSE)，并保留上游 OpenClash 及相关组件的版权声明。

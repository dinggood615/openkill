# OpenKill

OpenKill 是面向 OpenWrt 的轻量化 Mihomo（Meta）客户端 LuCI 插件，基于 OpenClash 兼容架构重构，提供稳定的代理接管、规则分流、双栈 DNS/IPv6 与可回滚运行管理。

当前版本：`2026-1098`

## 一键安装

安装、更新、卸载统一使用同一入口。默认进入菜单，也可以直接附加参数：

```sh
curl -fsSL https://raw.githubusercontent.com/dinggood615/openkill/master/i | sh
```

```sh
curl -fsSL https://raw.githubusercontent.com/dinggood615/openkill/master/i | sh -s -- --install
curl -fsSL https://raw.githubusercontent.com/dinggood615/openkill/master/i | sh -s -- --update
curl -fsSL https://raw.githubusercontent.com/dinggood615/openkill/master/i | sh -s -- --uninstall
```

安装器会自动识别 `opkg`/`apk`、设备架构和防火墙环境；短入口、依赖源和软件包源均会按可用性选择有效镜像，安装完整运行依赖，校验软件包 SHA256，并下载当前架构对应的官方稳定版 Mihomo/Meta 内核。安装完成后会自动刷新 GeoIP、GeoSite、ASN、IPv4/IPv6 大陆路由数据库，并在下载失败时保留软件包内的可用副本。更新会保留配置和上一份可用内核；卸载会移除 OpenKill 数据但不删除共享依赖。

## 功能

- Mihomo/Meta 官方稳定内核兼容：自动识别架构、校验版本与可执行文件，支持 TUN、规则和全局代理模式。
- 稳定启动链路：配置语义预检、原子替换、最近可用配置回滚、控制器/TUN/DNS/防火墙健康检查和有限次恢复。
- 轻量 watchdog：只观察 OpenKill 与 procd 状态，低频维护规则、历史和节点资源，带冷却窗口，避免重复拉起核心。
- 高效双栈网络：DNS、IPv6、Geo 数据、代理组测速使用有界超时和失败重试，降低首连等待与节点抖动。
- 流量接管互斥：统一管理 TUN、路由和防火墙；OpenKill 接管与 Mihomo 原生自动接管不能同时启用，可在界面切换。
- 规则与订阅管理：支持 GeoIP/GeoSite、大陆白名单、代理组分流、订阅更新、配置检查和安全回滚。
- 可选协议能力：按内核能力探测启用 H2C/ShadowQUIC、QUIC v2、MASQUE、AmneziaWG、AnyTLS、BBR3 和 ZeroTier 相关字段。
- LuCI 界面：运行状态、运行与服务、网络与分流、规则与订阅、性能与稳定、系统与维护分类；采用适配 Argon 深浅色模式的扁平卡片、统一间距和低干扰状态提示。
- 故障保护：缺少路由集合文件时自动创建兼容空集合，健康检查失败不覆盖上一份有效配置，日志记录每个安装与启动阶段。

## 兼容性

适用于带 `opkg` 或 `apk` 的 OpenWrt 固件。软件包与内核按设备架构和包管理器自动选择；厂商自带源保持原 ABI，标准 OpenWrt 源才会使用镜像回退。真实吞吐取决于固件、线路、节点和硬件能力。

## 许可

本项目遵循 [MIT License](LICENSE)，并保留上游 OpenClash 及相关组件的版权声明。

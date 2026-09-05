# OpenKill 与 Mihomo 兼容基线

OpenKill 只使用 [MetaCubeX/Mihomo](https://github.com/MetaCubeX/mihomo) 的官方稳定版内核。安装器每次安装或更新时读取官方 latest release，按设备架构下载并在替换前校验压缩包、可执行文件和配置；下载失败时保留现有内核。项目不再下载 Smart、OixCloud 或仓库内自行编译的内核。

## 稳定默认值

以下设置用于兼顾双栈网络、低延迟和低内存占用：

- `find-process-mode: off`：关闭逐连接进程查找，减少高并发时的 CPU 消耗。
- `unified-delay: true`、`tcp-concurrent: true`：统一延迟口径并允许地址竞速；节点组仍以成功的 HTTP 204 检测为准。
- TUN 使用 `stack: mixed`、自动路由/重定向，`endpoint-independent-nat: false`，避免为 NAT 映射付出额外开销。
- DNS 开启 IPv6，但保留 `ipv6-timeout`、国内/国外 `nameserver-policy` 和 `prefer-h3: false`，避免双栈首连被不可达的 IPv6 上游拖慢。
- `geodata-loader: memconservative` 和 `cache-algorithm: arc`，在内存有限的固件上降低 Geo 数据常驻占用。
- 自动组使用 300 秒周期、50 ms 容差、3 秒超时并关闭 lazy 检测；只有实际存在的节点会被测量，异常节点连续失败后才切换，减少抖动。

## 新内核能力的采用原则

Mihomo 的新字段会随内核版本变化。OpenKill 不把实验字段硬编码进所有固件，而是采用“检测后启用”的方式：

1. 启动前运行 `mihomo -t`（或等价的 OpenKill 配置预检）。预检失败时不替换当前配置，并恢复最近一次成功配置。
2. 内核更新只接受官方 stable release；安装器按架构匹配 `amd64-v1`、`arm64`、`armv7` 等资产，不能确认架构时停止而不是猜测。
3. 可选能力（例如 WireGuard/OpenVPN/MASQUE 的 `ip-stack`、Hysteria2 的握手超时、AnyTLS 元数据、`route-address-set`）只在目标内核明确支持且设备验证后，通过覆写配置启用；默认配置保持跨固件可解析。
4. 代理提供者的健康检查使用短超时和 `expected-status: 204`；规则仍按 Mihomo 自上而下的 first-match 语义排列。

## 四阶段实施对应关系

1. **配置验证、健康检查、回滚和 watchdog 防重启**：生成配置先做 YAML/Mihomo 预检；失败保留 last-good；watchdog 只观察 procd 和内核，不重复启动进程。
2. **拆分 watchdog、删除冗余功能、降低后台开销**：流媒体自动选择移到独立低频任务；删除 Smart/LightGBM 缓存入口；关闭不必要的进程扫描。
3. **DNS、IPv6、代理组测速和吞吐**：采用上述双栈 DNS 策略、固定节点地址族、短检测周期和有界失败重试。
4. **官方 Mihomo 特性兼容**：安装器动态跟随官方 stable release，静态校验和版本元数据统一，实验字段按能力检测后再启用。

官方参考：

- [General configuration](https://wiki.metacubex.one/en/config/general/)
- [DNS configuration](https://wiki.metacubex.one/en/config/dns/)
- [Proxy groups](https://wiki.metacubex.one/en/config/proxy-groups/)
- [TUN inbound](https://wiki.metacubex.one/en/config/inbound/tun/)
- [Proxy providers](https://wiki.metacubex.one/en/config/proxy-providers/)

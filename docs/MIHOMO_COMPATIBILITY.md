# OpenKill 与 Mihomo 兼容基线

OpenKill 只使用 [MetaCubeX/Mihomo](https://github.com/MetaCubeX/mihomo) 的官方稳定版内核。安装器每次安装或更新时读取官方 latest release，按设备架构下载并在替换前校验压缩包、可执行文件和配置；下载失败时保留现有内核。项目不再下载 Smart、OixCloud 或仓库内自行编译的内核。

## 稳定默认值

以下设置用于兼顾双栈网络、低延迟和低内存占用：

- `find-process-mode: off`：关闭逐连接进程查找，减少高并发时的 CPU 消耗。
- `unified-delay: true`、`tcp-concurrent: true`：统一延迟口径并允许地址竞速；节点组仍以成功的 HTTP 204 检测为准。
- TUN 默认使用 `stack: mixed`，并通过 UCI 的 `tun_owner` 选择唯一接管方：`openkill`（默认）写入 `auto-route: false`、`auto-redirect: false`，由 OpenKill 负责策略路由、防火墙和 DNS；`mihomo` 才同时写入两个 `true`，并完全停用 OpenKill 的自定义路由、防火墙和 DNS 接管。两种模式不能同时运行，`endpoint-independent-nat: false` 避免额外 NAT 开销。
- DNS 开启 IPv6，但保留 `ipv6-timeout`、国内/国外 `nameserver-policy` 和 `prefer-h3: false`，避免双栈首连被不可达的 IPv6 上游拖慢。
- 控制器默认绑定 `network.lan.ipaddr`，DNS 默认只监听 `127.0.0.1`；CORS 自动生成 LAN 与回环来源，不再使用 `*`。
- `geodata-loader: memconservative` 和 `cache-algorithm: arc`，在内存有限的固件上降低 Geo 数据常驻占用。
- 自动组使用 300 秒周期、50 ms 容差、5 秒单次超时、连续 3 次失败阈值并启用 lazy 检测；只有实际需要的节点会被测量，异常节点不会拖住整个组。

## 新内核能力的采用原则

Mihomo 的新字段会随内核版本变化。OpenKill 不把实验字段硬编码进所有固件，而是采用“能力探测 + 双重开关”的方式：

1. `/usr/share/openkill/openkill_capabilities.sh` 使用当前官方内核执行隔离的 `mihomo -t` 探测，结果缓存到 `/tmp/openkill/capabilities.env`，并在“插件设置 → Mihomo 能力”页面显示；内核文件变化后缓存自动失效。
2. 内核更新只接受官方 stable release；安装器按架构匹配 `amd64-v1`、`arm64`、`armv7` 等资产，不能确认架构时停止而不是猜测。
3. 全局开关位于“插件设置 → Mihomo 能力”：H2C/QUIC v2、ShadowQUIC、MASQUE 高级字段、AmneziaWG、AnyTLS `client-metadata`、BBR3 均默认关闭。节点页面还提供对应的高级开关；只有全局和节点开关同时打开时，写入脚本才会输出实验字段。
4. ShadowQUIC 的 QUIC 版本、0-RTT、拥塞控制、窗口和 MTU 字段按官方名称读写；VMess H2C 仅输出 `network: h2` + `tls: false`。MASQUE 和 ZeroTier 的 `ip-stack`、网络/回退、握手超时和 BBR 配置按官方层级输出，BBR3 还需要单独的 BBR3 开关。
5. YAML 导入会把 ShadowQUIC、MASQUE 高级字段和 WireGuard `amnezia-wg-option` 保存回 UCI；AnyTLS 元数据仅在显式开关打开时写入生成配置。节点分享链接支持 `shadowquic://` 的导入/导出，MASQUE 继续使用 YAML/“其他参数”以避免发明非官方 URI 格式。
6. 启动前仍运行 `mihomo -t`（或等价的 OpenKill 配置预检）。预检失败时不替换当前配置，并恢复最近一次成功配置。ZeroTier 使用 Mihomo 原生 `type: zerotier` 节点，受全局开关和节点字段控制；`/usr/share/openkill/openkill_zerotier.sh` 仅管理可选的固件系统 ZeroTier 服务，不列为硬依赖，也不会自动改写 Mihomo 路由。
7. 代理提供者的健康检查使用短超时和 `expected-status: 204`；规则仍按 Mihomo 自上而下的 first-match 语义排列。

ZeroTier 节点的 `network` 必须是 16 位十六进制网络 ID；可选的 `ip-stack`、端口回退、Orbit 和远程 DNS 字段均按官方层级写入。`h3-l4proxy` MASQUE 节点按官方限制强制关闭 UDP，避免生成可解析但无法工作的配置。

## 四阶段实施对应关系

1. **配置验证、健康检查、回滚和 watchdog 防重启**：生成配置先做 YAML/Mihomo 预检；失败保留 last-good；watchdog 只观察 procd 和内核，不重复启动进程。
2. **拆分 watchdog、删除冗余功能、降低后台开销**：流媒体自动选择移到独立低频任务；删除 Smart/LightGBM 缓存入口；关闭不必要的进程扫描。
3. **DNS、IPv6、代理组测速和吞吐**：采用上述双栈 DNS 策略、固定节点地址族、300 秒探测周期、5 秒单次超时和有界失败重试。
4. **官方 Mihomo 特性兼容**：安装器动态跟随官方 stable release，静态校验和版本元数据统一；能力探测、全局/节点双重开关、配置读写、原生 ZeroTier 节点和可选系统服务管理已经落地。

官方参考：

- [General configuration](https://wiki.metacubex.one/en/config/general/)
- [DNS configuration](https://wiki.metacubex.one/en/config/dns/)
- [Proxy groups](https://wiki.metacubex.one/en/config/proxy-groups/)
- [TUN inbound](https://wiki.metacubex.one/en/config/inbound/tun/)
- [Proxy providers](https://wiki.metacubex.one/en/config/proxy-providers/)
- [ShadowQUIC](https://wiki.metacubex.one/en/config/proxies/shadowquic/)
- [MASQUE](https://wiki.metacubex.one/en/config/proxies/masque/)
- [AnyTLS](https://wiki.metacubex.one/en/config/proxies/anytls/)
- [ZeroTier](https://wiki.metacubex.one/en/config/proxies/zerotier/)

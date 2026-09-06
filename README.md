<h1 align="center">
  <img src="https://raw.githubusercontent.com/dinggood615/openkill/master/img/logo.png" alt="OpenKill" width="200">
  <br>OpenKill<br>
</h1>

OpenKill 是基于 OpenClash 源码的 OpenWrt 客户端项目。

当前版本：`2026-1080`。

许可：本项目遵循 [MIT License](LICENSE)，并保留上游 OpenClash 及相关组件的版权声明。

安装、更新、卸载统一使用下面这一条入口；每条命令单独列出，GitHub 代码块右上角可直接复制：

菜单模式（选择安装、更新或卸载；GitHub 直连失败时自动切换 jsDelivr/FASTLY）：

```sh
tmp=/tmp/openkill-install.sh; ok=0; rm -f "$tmp"
for url in https://raw.githubusercontent.com/dinggood615/openkill/master/scripts/install-openkill.sh https://cdn.jsdelivr.net/gh/dinggood615/openkill@master/scripts/install-openkill.sh https://fastly.jsdelivr.net/gh/dinggood615/openkill@master/scripts/install-openkill.sh; do
  curl -fL --connect-timeout 8 --max-time 30 "$url" -o "$tmp" && grep -qx '# OpenKill installer' "$tmp" && { ok=1; break; }
done
[ "$ok" = 1 ] || { echo 'OpenKill installer download failed'; exit 1; }; sh "$tmp"
```

安装或修复：

```sh
tmp=/tmp/openkill-install.sh; ok=0; rm -f "$tmp"
for url in https://raw.githubusercontent.com/dinggood615/openkill/master/scripts/install-openkill.sh https://cdn.jsdelivr.net/gh/dinggood615/openkill@master/scripts/install-openkill.sh https://fastly.jsdelivr.net/gh/dinggood615/openkill@master/scripts/install-openkill.sh; do
  curl -fL --connect-timeout 8 --max-time 30 "$url" -o "$tmp" && grep -qx '# OpenKill installer' "$tmp" && { ok=1; break; }
done
[ "$ok" = 1 ] || { echo 'OpenKill installer download failed'; exit 1; }; sh "$tmp" --install
```

更新软件包和内核：

```sh
tmp=/tmp/openkill-install.sh; ok=0; rm -f "$tmp"
for url in https://raw.githubusercontent.com/dinggood615/openkill/master/scripts/install-openkill.sh https://cdn.jsdelivr.net/gh/dinggood615/openkill@master/scripts/install-openkill.sh https://fastly.jsdelivr.net/gh/dinggood615/openkill@master/scripts/install-openkill.sh; do
  curl -fL --connect-timeout 8 --max-time 30 "$url" -o "$tmp" && grep -qx '# OpenKill installer' "$tmp" && { ok=1; break; }
done
[ "$ok" = 1 ] || { echo 'OpenKill installer download failed'; exit 1; }; sh "$tmp" --update
```

卸载并清理：

```sh
tmp=/tmp/openkill-install.sh; ok=0; rm -f "$tmp"
for url in https://raw.githubusercontent.com/dinggood615/openkill/master/scripts/install-openkill.sh https://cdn.jsdelivr.net/gh/dinggood615/openkill@master/scripts/install-openkill.sh https://fastly.jsdelivr.net/gh/dinggood615/openkill@master/scripts/install-openkill.sh; do
  curl -fL --connect-timeout 8 --max-time 30 "$url" -o "$tmp" && grep -qx '# OpenKill installer' "$tmp" && { ok=1; break; }
done
[ "$ok" = 1 ] || { echo 'OpenKill installer download failed'; exit 1; }; sh "$tmp" --uninstall
```

更新统一使用 `--update`，会更新 OpenKill 软件包并安装/更新官方稳定 Meta（Mihomo）内核。

IPK/APK 构建完成后独立发布，互不等待。安装器会对软件包下载地址测速，验证发布清单，并在下载完成后校验 SHA256。页面源码版本可能领先于尚在构建的软件包，安装器显示实际选中的发布版本。
项目版本使用 `2026-1080` 形式；后续小改动递增 1，大改动跳到下一个整十（例如 `2026-1081` → `2026-1090`），APK 内部版本转换为 `2026.1080`，以满足 APK 包管理器的版本语法，数字序号保持同步。
安装器会显示系统检测、依赖审计、源验证、软件包下载、SHA256 校验、Mihomo 内核下载与最终服务验证的完整步骤。它会安装当前包管理器、当前防火墙模式所需的完整运行依赖；已满足的依赖不会重复刷新或下载。

依赖索引和安装共用临时源配置。仅标准 `downloads.openwrt.org` 源会尝试北大、清华镜像；厂商或自定义源保持原地址，避免下载到与当前固件或内核 ABI 不兼容的软件包。Mihomo 版本与 SHA256 从官方 Stable Release 获取，下载地址测速后再传输、校验、解压和验证可执行文件。

当前版本已按四阶段基线整理：

1. 配置预检、健康检查、最近可用配置回滚，以及只观察 procd 的 watchdog 防重复重启。
2. 拆分低频维护任务，移除 Smart/LightGBM 运行入口，关闭逐连接进程扫描，降低后台开销。
3. 双栈 DNS/IPv6、Geo 数据和代理组测速采用有界超时与失败重试，减少首连等待和节点抖动。
4. 通过官方 Mihomo stable release 动态获取内核，静态检查脚本与版本清单统一；新增能力探测和可选开关，按内核支持情况启用 ShadowQUIC/QUIC v2、MASQUE 高级参数、AmneziaWG、AnyTLS 元数据、BBR3 与原生 ZeroTier 节点。系统 ZeroTier 服务仍为独立可选项，不作为硬依赖。详见 [Mihomo 兼容基线](docs/MIHOMO_COMPATIBILITY.md)。

本次一次性整合（`2026-1060`）将四阶段收敛为可回滚的默认路径：生成配置先做语义检查再替换，控制器默认绑定 LAN 地址、DNS 默认仅监听回环地址，TUN 默认由 OpenKill 防火墙统一管理；需要时可在“运行与服务”中切换到互斥的 Mihomo 原生自动接管模式。watchdog 只观察 procd/核心状态，低频执行规则、历史、UPnP 和节点地址维护，并为 DNS 劫持修复加入冷却窗口。节点测速统一采用有界超时、204 探测和懒加载，避免单个失联节点拖慢整个面板。旧 Smart/LightGBM/OixCloud 参数在安装和更新时清理，官方 Mihomo 内核仍按设备架构独立校验下载。

安装器遇到缺失路由集合文件会先创建兼容的空集合定义；升级备份不完整时不会执行无条件移动或读取，因此不会再因 `china_ip_route.ipset` 缺失而中断启动。

验证顺序固定为：静态 shell/YAML 检查 → 生成配置语义检查 → Mihomo `-t`（可用时）→ 原子替换并保存 last-good → procd 启动与 watchdog 观察。任一步失败都会保留上一份可用配置，不会自动反复启动第二个核心进程。

2026-1060：一次性整合四阶段稳定性、轻量化、双栈网络和官方 Mihomo 兼容方案；新增事务化配置语义校验、安全监听默认值、TUN 路由自适应开关、路由集合缺失保护、测速有界默认值和 watchdog 低频/冷却机制。

2026-1080：统一生成与运行地址解析，按有效配置检查内核实例、控制器、TUN、DNS 和防火墙；启动使用统一等待时限及一次检查点恢复，独立低频健康观察，升级内核前验证有效配置并保留上一内核。发布前增加官方稳定内核配置与本地代理测试。真实固件稳定性和吞吐仍需实测，详见 [验证与验收说明](docs/RUNTIME_ACCEPTANCE.md)。

2026-1072：修复配置状态路径误判、LAN/CIDR 监听地址解析不一致、健康检查受系统代理干扰、原生 TUN 路由表误判和失败回滚覆盖问题；缩短无效 TUN 重试并修正未带时间戳日志的错误级别。

2026-1070：一次性落地稳定运行方案；统一 UCI 生效值和 IPv6/TUN/DNS 约束，增加核心 API 健康检测与面板地址校验，修复多种 Mihomo 进程名导致的控制面板误判，完善依赖清单、能力缓存失效和原子回滚，并补齐新增插件设置的中文翻译。

2026-1061：重构插件设置页布局；将五个分类整理为运行与服务、网络与分流、规则与订阅、性能与稳定、系统与维护，并在分类内加入统一卡片、折叠、高级项收纳和响应式字段布局，不改变 UCI 字段、依赖条件或运行逻辑。

2026-1055：将插件设置整理为基础运行、网络与分流、规则与资源、稳定与性能、高级与维护五个分类；新增设置搜索、匹配计数和高级分类折叠，保留原有字段与保存逻辑。

2026-1054：统一运行状态页与插件设置页的视觉基础；移除状态页多余外层间距，新增设置页卡片、紧凑标签、输入控件和响应式样式，不改变运行逻辑。
2026-1053：修复部分 OpenWrt Ruby 不支持数组直接比较导致安装器在汇总多个版本清单时中止的问题；改用兼容的数字分量比较。
2026-1052：进一步防止旧 CDN 清单造成版本回退；清单低于安装器版本时，自动核对 GitHub Releases API（含备用代理入口），发现更高发布版本后优先使用。
2026-1051：修复 CDN 缓存旧版软件包清单导致一键安装回退到旧版本的问题。清单请求加入防缓存参数，汇总并校验所有源后选择最高版本，再使用最快有效源下载软件包。
2026-1050：重构一键安装与官方 Mihomo 内核下载。依赖按系统/防火墙完整审计并批量安装；标准固件源可测速回退，厂商源保持 ABI 兼容；软件包和内核显示下载进度、选择最快有效地址，并执行 SHA256、压缩包与可执行文件校验。README 安装入口增加 GitHub、jsDelivr、FASTLY 自动回退。
2026-1042：补齐 MASQUE 节点 SNI 的表单显示与 YAML 导入/导出，保留官方 TLS 配置的完整性。
2026-1041：修复 VMess H2/H2C 的双重开关保护；未同时启用全局与节点 H2C 时，自动保持 TLS，避免旧配置或导入配置意外降级为明文 H2。
2026-1040：第四阶段能力真正接入；新增内核能力探测、ShadowQUIC/QUIC v2、H2C、MASQUE 高级参数、AmneziaWG、AnyTLS 元数据、BBR3 及 ZeroTier 可选开关，并完成节点 UCI/YAML 读写。

2026-1032：修复依赖源重复声明和旧备份缺少路由集合文件的问题；依赖、软件包和官方内核下载增加快速失败与镜像回退，已安装依赖时跳过无必要的源刷新。
2026-1033：修复启动前 Mihomo 配置预检未继承 SAFE_PATHS，导致 external-ui 路径被拒绝、OpenKill 无法启动的问题；统一预检、订阅校验和运行时的安全路径。
2026-1031：按四阶段基线更新 UI；状态页显示官方内核、IPv6/DNS 与 watchdog 配置摘要，版本页改为自动匹配官方 Mihomo 稳定内核，并移除已停用的使用帮助浮层。
2026-1030：完成四阶段稳定性、轻量化、双栈 DNS/测速和官方 Mihomo 兼容基线；新增配置预检/回滚、独立 watchdog 任务与 CI 静态检查。
2026-1020：隔离旧版本缓存，避免升级后继续显示上游 OpenClash 版本列表。
2026-1019：修复版本更新列表仍读取上游 OpenClash 版本的问题，改为读取 OpenKill 自有仓库。
2026-1018：移除运行状态页公告栏并收紧布局间距，减少页面空白和无用请求。
2026-1017：缓存内核版本查询并降低状态页轮询频率，减少 LuCI 与内核短时 CPU 开销。

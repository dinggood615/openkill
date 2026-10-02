# Current status

## 2026-10-02 2026-1208 严格 DNS 启动重试与 Mihomo v1.19.32 正式包验收

- 重新核实基线为 `ab7c04d2b6cbab8b6e1cbf942a33c4a892e4bdd7`，本轮修复提交为
  `b1d771dbbed9566583031aa2cf67d81e3de04cb9`；工作区仍只保留既有未跟踪的
  `.rc-*` 审计目录，未修改或纳入提交。
- 复现根因：核心、控制器和 DNS 监听已经就绪时，严格 DNS 的只读运行查询只有一次机会；
  代理链瞬时不可达会写入 `startup-failed` 并停止服务。分流模式能启动，严格模式在上游
  不可达时按设计闭锁，未观察到核心架构或 mips/BBR3 配置错误。
- 修复 `luci-app-openkill/root/etc/init.d/openkill`：增加三次、间隔 2 秒的有界严格
  DNS 运行证据重试；持续失败仍拒绝报告服务就绪，不生成配置、不分配端口、不回退到
  明文 DNS 或 `DIRECT`。`scripts/test-runtime.py` 增加对应回归契约。
- 版本同步为 `2026-1208`（Makefile、安装器、README），新增
  `docs/release/notes/2026-1208.md`。核心 profile 迁移标记仍为 `2026-1207`，避免
  在每次重装时重复迁移用户配置。
- 本地 WSL 运行时测试 35 项、DNS 语义 6 项/10 assertions、LuCI 合同 32 项、安装器
  15 项及 `scripts/local-gate.sh` 均通过；Windows 直接调用 Linux shell 的失败未计入，
  已在 WSL 同等环境复验。
- 精确提交 Development CI `36959035974` 成功：
  https://github.com/dinggood615/openkill/actions/runs/36959035974 。RC Build
  `36959151891` 成功：
  https://github.com/dinggood615/openkill/actions/runs/36959151891 。候选 IPK
  `luci-app-openkill_2026-1208_all.ipk` 大小 7,722,229 bytes，SHA256
  `48004f7a74b7d0c43c6552eb109b838d2ce4758bf61815ddbc2f5898622d22c2`；包内容、维护
  脚本、conffile 保留及敏感数据审计通过。
- Formal Release `36959986012` 成功：
  https://github.com/dinggood615/openkill/actions/runs/36959986012 。正式标签与 Release
  为 `v2026-1208-ipk`：
  https://github.com/dinggood615/openkill/releases/tag/v2026-1208-ipk ，源提交为
  `b1d771dbbed9566583031aa2cf67d81e3de04cb9`。正式 IPK 大小 7,924,954 bytes，SHA256
  `95cc200be4bb5a5cae1ac0dc1083b89f67cbbbe8815835725a8e521675515718`；package channel
  `master/latest-ipk.json` 同步到该版本、提交和哈希。
- 授权测试机 192.168.1.103 已使用 `opkg --force-reinstall` 实际替换正式包，`opkg`
  显示 2026-1208；设备 `/etc/init.d/openkill` 与严格 DNS 运行检查脚本的 SHA256
  与正式 IPK 解包文件一致。用户 conffile、独立 Naive 数据和既有 YAML 均保留。正式
  安装后的最终状态为 `running`，Mihomo Meta v1.19.32，当前用户明确保留的运行配置为
  `mixed` TUN 与 `bbr3`（未擅自覆盖用户选择）；新安装/由 OpenKill 管理的默认配置仍为
  `mips`＋`bbr3`，严格 DNS state 为 `runtime_verified=1`。
- 正式包安装后重复启停出现过严格 DNS 上游不可达导致的 `startup-failed`，随后重试在
  同一包、同一配置下成功；这证明新增重试改善了瞬时竞态，但不能消除远端代理不可用。
  分流模式下核心可稳定运行；独立 Naive SOCKS5 经两个 HTTPS 目标返回成功（一个目标
  返回 200，另一个返回正常重定向）。当前设备源 YAML 中的本地 SOCKS5 节点没有被任何
  Mihomo 代理组引用，且现有 Mihomo 远端组的 HTTPS 请求失败；这是用户配置/远端可用性
  限制，不是本轮 v1.19.32 适配代码的凭据或启动缺陷。未擅自改写用户 YAML 或默认代理组。
- Chrome 用户会话在当前工具环境不可见，因此真实 LuCI 视觉逐页验收（七个设置页、缩放、
  主题）仍标记为未验证；SSH/HTTP 检查未替代该项。已完成设备进程、加载配置、核心版本、
  DNS 运行状态、正式包真实安装及独立 Naive 网络冒烟。
- 受保护备份继续保留在 `/root/openkill-mihomo-backup-20261002`（目录 700、敏感文件
  600），包含重装前后配置、核心/包状态、运行日志和恢复材料；回滚可安装
  `v2026-1207-ipk` 并恢复该备份。未授权整机重启、WAN/DNS 防火墙策略或其他插件配置。

## 2026-10-02 2026-1207 Mihomo v1.19.32 适配（发布门禁进行中）

- 基线重新核实为 `dad7c329a6825cf4f2b48398da7c65dfe74c508e`，源版本为
  `2026-1206`；工作区仅保留此前未跟踪的 `.rc-*` 审计目录，未修改或纳入本轮提交。
- 已完成代码阶段：TUN 允许 `mips`，新安装默认 `mips + bbr3`；IPv4/IPv6 选择共享
  实际 TUN 配置；旧 `system/mixed` 默认组合通过一次性 `mihomo_profile_version`
  迁移；核心低于 v1.19.31/v1.19.32 时分别使用有界 `mixed/cubic` 或 `mixed/bbr`
  兼容回退，并记录原因。
- 已移除协议生成器对 H2C、ShadowQUIC、MASQUE、AmneziaWG、AnyTLS metadata、
  BBR3 和 Mihomo 内置 ZeroTier 的全局 feature 门槛。旧 UCI 键仍保留，但不再决定
  节点字段是否输出。能力页改为只读核心与兼容摘要，协议选项归入节点编辑。
- 受影响文件包括 `settings.lua`、`settings_theme.htm`、`servers-config.lua`、
  `openkill_semantic_check.sh`、`yml_change.sh`、`yml_proxys_set.sh`、核心能力探测、
  init 迁移逻辑、默认 YAML、UCI 默认配置及测试脚本。
- 已通过：WSL 中 `scripts/test-runtime.py` 34 项（3 skip）、官方 Mihomo v1.19.31
  与 v1.19.32 `scripts/test-core.py` 各 12 项、LuCI 合同 32 项、安装测试 15 项、
  UCI 生命周期 19 项、核心下载契约 4 项、测试门禁 25 项，以及
  `sh scripts/local-gate.sh`。Windows 直接执行 Linux 核心的失败仅为宿主格式限制，
  已用 WSL 同等环境复验。
- 版本已从 `2026-1206` 提升为 `2026-1207`，发布说明为
  `docs/release/notes/2026-1207.md`。尚未完成精确提交 CI、RC 构建、测试机安装和
  Formal Release；这些是下一阶段的硬门禁，不能以当前本地测试代替。

## 2026-10-01 2026-1206 UI 字段顺序与运行状态页宽度（正式验收完成）

- 本轮严格限定为 LuCI UI：未修改 DNS 机制、NaiveProxy、核心启动、WAN、路由、TUN、
  防火墙或其他网络策略。两个问题的根因均已重新以真实 DOM 验证：
  `settings_theme.htm` 的卡片筛选保留 CBI 定义顺序，字段定义顺序错误会使“专用 DNS
  代理组名称”离开目标位置；运行状态页底部 wrapper 使用了不同的宽度约束。
- 修复文件：`luci-app-openkill/luasrc/model/cbi/openkill/settings.lua` 将
  `dns_privacy_group` 定义移动到 `enable_custom_domain_dns_server` 之前，使两者在同一
  卡片中相邻；`luci-app-openkill/luasrc/view/openkill/settings_theme.htm` 与
  `luci-app-openkill/root/www/luci-static/resources/openkill/css/flat.css` 延续统一的
  `--ok-client-content-max` 宽度契约；`scripts/test-ui-contract.py` 增加字段顺序回归断言。
  版本同步为 `2026-1206`，发布说明为 `docs/release/notes/2026-1206.md`。
- 源提交 `5bb6035de0a20140a47c77945d0b394f4ca9e5ea` 已推送。精确提交的 Development CI
  `36837056398`：
  https://github.com/dinggood615/openkill/actions/runs/36837056398 。RC Build
  `36837272712`：
  https://github.com/dinggood615/openkill/actions/runs/36837272712 ，候选 IPK
  `luci-app-openkill_2026-1206_all.ipk` 大小 7,721,136 bytes，SHA256
  `08b03486aa7b6fdf9c0e02a535fc035ef337391b037636223b0a6a3fde38ec15`，包内容审计、
  conffile 保留、维护脚本删除审计及运行时敏感数据审计均通过。
- Formal Release `36838471667`：
  https://github.com/dinggood615/openkill/actions/runs/36838471667 ；正式标签与
  Release 为 `v2026-1206-ipk`：
  https://github.com/dinggood615/openkill/releases/tag/v2026-1206-ipk 。正式包大小
  7,925,972 bytes，SHA256
  `279b7fa5e9912f9fe29a38efe0afcf19616a2ef9d681e58b2a80874ad8fa8e98`，下载地址：
  https://github.com/dinggood615/openkill/releases/download/v2026-1206-ipk/luci-app-openkill_2026-1206_all.ipk 。
  RC 与正式包因构建时间元数据不同，哈希分别记录，未声称相同。
- 授权测试机 192.168.1.103 已先安装候选包，再通过 LuCI 上传正式包并使用包管理器支持的
  `opkg --force-reinstall /tmp/upload.ipk` 实际替换同版本正式包；设备 `opkg status`
  显示 `2026-1206`，安装时间更新，且设备三个关键 UI 文件 SHA256 与正式包解包内容一致。
  用户 conffile `/etc/config/openkill` 被保留，维护脚本产生的服务不存在提示已记录，未扩大
  本轮修改范围。
- 正式包安装后真实 LuCI 验收：字段唯一出现，`dns_privacy_group` 的 DOM 索引为 6、
  `enable_custom_domain_dns_server` 为 7，前者的下一个兄弟节点即后者；刷新后现有字段值
  保持一致。使用该现有值实际点击“保存配置”后仍留在设置页且刷新重读一致；点击“应用配置”
  正常跳转到运行状态页，但页面继续显示既有核心“启动失败”，这正是本轮范围外的历史状态。
  运行状态页 `.openkill-status-page` 与 `.openkill-myip-page` 在当前视口均为
  `x=228,width=558`，页面资源版本为 `2026-1206`，无横向滚动（scrollWidth 816）。
  本地 32 项 UI 合同、2 项预览、浏览器/交互/Naive UI 测试、`git diff --check` 与
  `scripts/local-gate.sh` 全部通过；浏览器当前会话未能可靠改变实际视口，因此不同缩放档位
  未冒充已覆盖，已由 CSS/本地响应式契约测试覆盖。
- 设备设置页与运行状态页均可正常渲染；页面仍显示既有核心“启动失败”，该状态在本轮明确
  排除且未修复，不能将本次 UI 发布描述为核心或网络故障修复。DNS、NaiveProxy、用户 YAML、
  节点和服务策略未因 UI 变更被修改。
- 受保护备份保留在 `/root/openkill-ui-backup-20261001`（目录 700、备份文件 600），
  覆盖原配置、相关 Lua/模板/CSS 和包状态；回滚可安装上一正式标签或恢复该备份。正式包
  安装前后的现有配置保持策略未改动。

## 2026-10-01 2026-1203 专用 DNS 代理组与加密引导正式验收（完成）

- 本轮实现已锁定于源提交 `55694492a9281ea7e4ed648462da17bc49267bfa`：严格隐私模式
  生成不含 `DIRECT` 的专用 DNS 代理组，普通解析、节点解析和引导解析分别校验；
  运行时只读检查在应用后验证实际加载配置、代理组成员和受控 DNS 查询，失败时不报告
  就绪。配置生成、状态接口和 LuCI 均不保存或输出凭据，保留原有用户组、节点和 YAML。
- 本地质量门禁及 6 项 DNS 语义测试（10 assertions）通过；精确源提交的 Development
  CI `36828775582`：
  https://github.com/dinggood615/openkill/actions/runs/36828775582 ；RC Build
  `36828918058`：
  https://github.com/dinggood615/openkill/actions/runs/36828918058 ；Formal Release
  `36830029976`：
  https://github.com/dinggood615/openkill/actions/runs/36830029976 。
- 候选 IPK `luci-app-openkill_2026-1203_all.ipk` 大小 7,720,932 bytes，SHA256
  `330d1b7adde625bc4a6665df27473a3a2be0191788e591d53b1753acc52ba8b0`。正式 Release
  标签与资产为 `v2026-1203-ipk`：
  https://github.com/dinggood615/openkill/releases/tag/v2026-1203-ipk ；正式包大小
  7,925,976 bytes，SHA256
  `1bb15e436961e5ac5a7dc7d0c6984848e16e61c60113854fe81902da7c6d2a11`，下载地址：
  https://github.com/dinggood615/openkill/releases/download/v2026-1203-ipk/luci-app-openkill_2026-1203_all.ipk 。
  正式包内容审计未发现测试机地址、真实节点主机、分享凭据或个人节点数据。
- 授权测试机 192.168.1.103 已使用 `opkg --force-reinstall` 实际替换正式包，包版本为
  2026-1203；服务停止后进程和状态文件消失，再启动返回成功。正式安装后的运行状态为
  `configured=1/effective=1/runtime_verified=1`，受控 DNS API 查询返回 status 0，
  Mihomo HTTPS 与独立 Naive SOCKS5 HTTPS 均返回 204。正式安装后在 WAN 接口进行有界
  采集，测试窗口未观察到外发明文 53/853；这证明本次链路未出现该窗口内的旁路，不能
  扩大为所有客户端、浏览器 DoH、服务停止期间或完整 IPv6 数据面的绝对“零泄漏”保证。
- 真实 LuCI 页面已刷新到 `v2026-1203` 并复核状态卡片：DNS 隐私“已开启”、NaiveProxy
  “已开启”、OpenVPN/RustDesk“已关闭”，广告拦截在缺少可靠生效证据时保持“—”；页面
  仍显示状态获取失败时的保留/未验证语义。正式包安装后页面、DNS 状态和联网冒烟均通过。
- 受保护设备备份保留在 `/root/openkill-dns-proxy-backup-20261001`（目录 700、敏感
  文件 600），归档 SHA256 为
  `aa028efa6ba3cf5a98f918fdde71efb5837e91fb60a8cea3a46410d8c91e570d`。回滚可从该备份
  恢复配置并安装上一正式 IPK；正式包同版本替换使用了强制重装，未把“已是最新”作为
  安装证据。
- 使用方式：升级并重载后，在 DNS 隐私设置选择严格模式并应用；OpenKill 会生成专用
  DNS 代理组并在运行时验证，代理组无可用成员时拒绝报告就绪。分流模式仍按其允许的
  直连边界工作，不能称为绝对无泄漏。未覆盖的外部客户端 DoH、完整 IPv6 抓包和 Chrome
  原生会话缩放需在对应环境另行验收。

## 2026-10-01 专用 DNS 代理组与加密引导改造（实施过程记录）

- 用户明确授权在 192.168.1.103 进行本轮 DNS 相关备份、应用及验收；不授权新增
  防火墙、路由、WAN 或 TUN 策略。受影响契约为 DNS YAML 生成、语义校验、只读状态
  及升级保留。保留现有用户配置与未跟踪 `.rc-1200-audit/`。
- 基线 HEAD 为 `45fcd20`。先补行为测试，再实现不含 DIRECT 的专用组、无循环的
  加密引导和真实加载证据，执行精确提交 CI、RC 设备验收，再进入正式发布。
- 纠正历史结论：effective=1、Fake-IP 和 AAAA 抑制仅证明部分配置/入口行为，不能
  证明上游代理链或 DNS 无泄漏；2026-1201 的 IPv6 描述是风险修复，不是已经抓包
  确认的唯一泄漏根因。本轮尚未完成包级泄漏验收。
- 已实现第一版 `dns_privacy.rb` 转换及 6 项行为测试（10 assertions），本地质量
  门禁通过，既有 runtime 33 项通过。严格组只含具体非直连代理，排除 dialer 依赖
  和本地 SOCKS 桥以防外部组件 DNS 循环；provider-only 暂明确拒绝。生成证据不再
  自称 effective，仍需补充真实加载版本与验证结果接口。
- 已确认测试机 Kwrt 25.12-SNAPSHOT x86/64，Mihomo v1.19.31，备份
  `/root/openkill-dns-proxy-backup-20261001/configs.tar.gz`，SHA256
  `aa028efa6ba3cf5a98f918fdde71efb5837e91fb60a8cea3a46410d8c91e570d`。
  当前核心接受专用组/IP-literal DoH 配置；直接 DoH 请求在证书校验开启时 HTTP200，
  候选 API reload HTTP204，真实 DNS status0/answer1，HTTPS204/200。
- 安装 tcpdump-mini 用于有界诊断；受保护 WAN 采集窗口记录 TCP24、53端口0。
  这是单个有限窗口，不证明所有查询和 IPv6 无泄漏；最初缓存窗口零包不计入成功
  证据。候选临时加载后恢复原运行 YAML；未修改网络规则，未发布。
- 待完成：清理旧生成器的重复规则逻辑、完整参数/引导语义校验、加载状态证据、
  故障场景与 IPv6 测试、真实 LuCI 保存应用、精确提交 CI、RC 安装与正式发布。

## 2026-10-01 2026-1202 NaiveProxy 状态卡片解析修复与最终包验收

- 2026-1201 正式包页面复核发现真实清单包含 1 个 enabled/running 实例，但卡片仍为
  “已关闭”。根因是 Lua 清单解析把 `|` 当作正则交替；Lua pattern 不支持该语法，
  `enabled=(1|true|yes|on)` 永远匹配不到。`openkill.lua` 现改为字段提取和显式布尔归一化，
  失败健康值也按独立等值判断，未读取或输出节点凭据。
- 新增运行时回归测试，禁止再次引入该模式；本地运行时测试 33 项（2 项按环境跳过）和
  `scripts/local-gate.sh` 均通过。候选安装后的真实 LuCI 页面显示 DNS“已开启”、NaiveProxy
  “已开启”、未启用项“已关闭”，未确认广告拦截保留 `—` 并在卡片外提示；五张卡片详情均
  隐藏，页面控制台无 error/warning。状态与实例证据对接正确。
- 源提交 `2756e8344a04687b515b0299ede41b2a374434b6`；Development CI
  `36813061558`：
  https://github.com/dinggood615/openkill/actions/runs/36813061558 ；RC Build
  `36813233460`：
  https://github.com/dinggood615/openkill/actions/runs/36813233460 ；Formal Release
  `36813550762`：
  https://github.com/dinggood615/openkill/actions/runs/36813550762 。正式标签与 Release
  为 `v2026-1202-ipk`：
  https://github.com/dinggood615/openkill/releases/tag/v2026-1202-ipk 。RC IPK
  SHA256 为 `28aebcdc7a5a59b14e386f2632e9190e9c5ff92820921cac7edd53e1bea405c6`；正式
  `luci-app-openkill_2026-1202_all.ipk` 大小 7,728,389 bytes，SHA256
  `1a11702f580958f8fa1d8eeeeb4788842515cd89339865bfd23c385316473338`，下载地址：
  https://github.com/dinggood615/openkill/releases/download/v2026-1202-ipk/luci-app-openkill_2026-1202_all.ipk 。
- 2026-1202 RC 与正式 IPK 均通过 `opkg --force-reinstall` 在授权设备实际替换；最终
  包状态为 2026-1202、服务 running。正式包安装后严格 DNS 状态仍为 effective=1、
  `filter_aaaa=1`、IPv6 DNS 重定向存在，受控 IPv4 A 查询返回 198.18/受控地址；独立
  Naive SOCKS5 HTTPS 返回 204，当前 Mihomo SOCKS5 HTTPS 返回 200；停止后核心 PID
  消失，再启动返回 0 并恢复，重启后 HTTPS 返回 204。既有 Naive 数据、用户配置和
  YAML 未被清理。正式包审计未发现个人节点、凭据或测试机数据。
- 设备受保护备份仍为 `/root/openkill-dns-ui-backup-20261001082205`（目录 700、归档
  600），归档 SHA256 为
  `b1ae76ce827ef843912eec11f7c01fff96ae5a7c30d499de8a3a1e8e156a3849`。完整 IPv6
  数据面抓包、外部客户端 DoH 旁路及 Chrome 原生会话视觉验收仍未覆盖；IAB 真实 LuCI
  DOM/计算样式/脚本验收已通过，不能把这些限制描述为已验证。

## 2026-10-01 2026-1201 运行状态布局、二元卡片与严格 DNS 修复

- 本轮复核确认截图中的黑色横条和宽度差来自 IP 地址页面仍嵌套的 CBI
  `fieldset/table/td` 视觉壳，而不是内部 IP 卡片；`myip.htm` 已改为与运行状态页
  同一语义内容列，`flat.css` 只在 OpenKill 页面范围内清除旧壳的背景、边框、阴影和
  宽度限制。真实 LuCI 页面计算盒模型显示运行状态与 IP 区域均为
  `x=228,width=1022.4`，背景透明、无边框/阴影，`fieldset` 数量为 0；正式包页面
  重载后结果相同。
- 五张功能卡片由 `status.htm` 的证据模型驱动：可靠证据只显示“已开启”或“已关闭”，
  证据不足保留 `—`/上次可靠二元结果，并把失败提示放在卡片外；卡片详情始终隐藏。
  DNS、广告拦截、OpenVPN、RustDesk 和独立 NaiveProxy 分别检查自己的配置及应用/运行
  证据，不由核心状态互相推断。真实页面正式包复核显示 DNS“已开启”、未确认的广告拦截
  显示 `—`、其余未启用项显示“已关闭”；请求失败时不会伪造关闭状态。
- 真实页面刷新后的浏览器日志为空；订阅接口返回空响应时此前的
  `null.providers` JavaScript 异常已在 `status.htm` 做空值归一化。IAB 真实 LuCI 页面
  完成了 DOM、计算样式、状态卡片和脚本复核；本机 Chrome 桥接当时不可用，因此不把
  Chrome 原生截图/控制台作为已验证证据。
- DNS 泄漏根因是严格模式在 IPv6 代理关闭时只保护了 IPv4，且没有保存/恢复 dnsmasq
  `filter_aaaa` 原值；IPv6 TCP/UDP 53 和 AAAA 响应可形成绕过。`openkill` 现在在该
  精确组合下只增加 fw4 IPv6 DNS 重定向并临时过滤 AAAA，停止时按存在性元数据恢复；
  `yml_change.sh` 生成加密的普通 `nameserver/fallback`，并以无凭据状态文件记录
  有效性及明确的节点引导解析例外。没有改 WAN、路由、TUN 或全网代理策略。
- 授权测试机 `192.168.1.103` 为 Kwrt/OpenWrt 25.12-SNAPSHOT x86/64。正式包安装前
  受保护备份位于 `/root/openkill-dns-ui-backup-20261001082205`（目录 700、归档 600），
  `configs.tar.gz` SHA256 为
  `b1ae76ce827ef843912eec11f7c01fff96ae5a7c30d499de8a3a1e8e156a3849`。备份未进入 Git、
  构建缓存或发布附件。
- 候选包 `luci-app-openkill_2026-1201_all.ipk` SHA256 为
  `7325a1ae730e86ad306ab9a84be426a9e01255e73520854450768d724c307559`；候选审计通过，
  未发现个人节点、凭据或测试机数据。候选已通过 `opkg --force-reinstall` 实际安装，
  包版本 2026-1201，服务 running；严格模式生成 `effective=1` 状态、普通解析为加密
  DoH、IPv4/IPv6 DNS 规则和 `filter_aaaa=1`。来自 LAN 的 IPv4 与 IPv6 DNS A 查询均
  返回受控地址，AAAA 查询无回答；没有 tcpdump 工具，完整 IPv6 数据面包级抓包及外部
  客户端 DoH 旁路仍标记为未覆盖。
- 候选安装后页面停止/启动各返回 0，核心停止时 PID 消失、再次启动恢复；Mihomo
  SOCKS5 通过两个 HTTPS 目标返回 HTTP 204/200，独立 Naive SOCKS5 通过 HTTPS 返回
  HTTP 204。正式包重复安装后包版本为 2026-1201、服务 running，停止/启动及 Mihomo
  HTTPS 冒烟再次通过；没有新增持续崩溃或无限重启证据。
- 源提交 `aab649a7481d9edf3962f03bfa5beaeea2c4deee`。Development CI
  `36810348305`：
  https://github.com/dinggood615/openkill/actions/runs/36810348305 ；RC Build
  `36810571519`：
  https://github.com/dinggood615/openkill/actions/runs/36810571519 ；Formal Release
  `36811899879`：
  https://github.com/dinggood615/openkill/actions/runs/36811899879 。正式标签
  `v2026-1201-ipk` 与 Release：
  https://github.com/dinggood615/openkill/releases/tag/v2026-1201-ipk 。正式 IPK
  `luci-app-openkill_2026-1201_all.ipk` 大小 7,924,016 bytes，SHA256
  `8b4c9b99ee1ac69a56d9210c549d0054adfb47d0e32e308b79412879fad6227f`，下载地址：
  https://github.com/dinggood615/openkill/releases/download/v2026-1201-ipk/luci-app-openkill_2026-1201_all.ipk 。
  正式包已在授权测试机通过 `opkg --force-reinstall` 实际替换并完成页面、DNS 和联网冒烟。

## 2026-10-01 2026-1200 运行状态 UI 状态证据与布局修复

- 本轮范围限定为运行状态页面 UI；没有修改 NaiveProxy 生命周期、节点配置、
  DNS、防火墙、路由、WAN、TUN 或默认代理策略。截图中的状态误导根因是旧
  前端把“已配置/已生成”、字符串布尔值及缺失字段混同为启用，且状态详情被
  CSS 隐藏；IP 地址/访问检查则仍套在 CBI 外层 fieldset/table 视觉容器中，
  产生额外黑色背景、边距和宽度收缩。
- 修复提交 `82522c756b8217e028ba333c011e5c1b807fd14b`：
  `luci-app-openkill/luasrc/view/openkill/status.htm` 增加统一证据状态模型
  （开启、关闭、待验证、异常、未知），严格区分缺失、布尔/数字/字符串和
  运行/验证证据；`luasrc/controller/openkill.lua` 仅增加脱敏的
  `naive_manifest_present` 只读字段；`oc.css` 显示次级证据；
  `myip.htm`/`flat.css` 仅对 OpenKill 页面移除外层 CBI 视觉壳并恢复统一宽度，
  保留内部卡片、操作和响应式结构。未以页面颜色推断 Naive 远端联网。
- 本地门禁：UI contract 31 项、preview 2 项、interaction 1 项、Naive UI
  browser contract、OpenKill test gates 25 项、Naive integration、UCI
  lifecycle、UI browser/production JS/dimensions/local requests 及
  `scripts/local-gate.sh` 均通过；Windows 环境不能替代 Linux/BusyBox 运行时
  集成测试，精确提交的 CI 为最终门禁。
- 受保护 UI/配置备份位于设备
  `/root/openkill-ui-backup-20261001003906`（目录 700、归档 600），归档
  SHA256 为 `9271e1320c107ad096edc43eb1221618b97bdc5d24817a8692a039a514392163`。
  备份不在 Git、构建缓存或发布附件中。
- RC Build `36746091821` 通过，候选 IPK 已强制安装并验证；随后正式 Release
  `36746897917` 通过。正式标签 `v2026-1200-ipk` 指向上述源提交，正式 IPK
  `luci-app-openkill_2026-1200_all.ipk` 大小 7,913,873 bytes，SHA256
  `875be4dbbf417d19b0d31f50aaf6e0d4a70cb0ca74c2f8d3e9cc14a184b12d00`，
  下载地址为
  https://github.com/dinggood615/openkill/releases/download/v2026-1200-ipk/luci-app-openkill_2026-1200_all.ipk 。
  包频道 `master/version` 与 `master/latest-ipk.json` 已同步版本、提交、URL
  和哈希。
- 正式包在授权测试机通过 `opkg --force-reinstall` 实际替换（事务返回 0，
  包状态为 2026-1200，服务为 running）；认证状态接口及 client/settings
  页面均返回 HTTP 200。既有 Mihomo SOCKS5 入口在正式包安装后对两个 HTTPS
  目标返回 HTTP 204/200，退出码均为 0，作为 UI 发布回归证据；本轮没有把它
  解释为 NaiveProxy 网络问题已修复。
- Development CI `36745905015`：
  https://github.com/dinggood615/openkill/actions/runs/36745905015 ；RC：
  https://github.com/dinggood615/openkill/actions/runs/36746091821 ；Formal：
  https://github.com/dinggood615/openkill/actions/runs/36746897917 ；Release：
  https://github.com/dinggood615/openkill/releases/tag/v2026-1200-ipk 。
- 设备 HTTP/API、包内容和服务状态已复核；当前 Chrome computer-use 桥接持续
  返回 request-header policy 错误，无法取得真实浏览器截图或控制台证据。因此
  深浅主题、窄屏和键盘的自动化/源码契约已通过，但本轮真实 Chrome 视觉验收
  标记为未验证，不能用 HTTP 200 冒充。此前独立 Naive 远端链路也不属于本轮
  UI 范围，保持历史限制记录。

## 2026-09-30 2026-1199 重装后核心启动修复与正式包验收

- 本次重新复现了“重新安装后无法启动”的实际根因：旧版
  `/etc/config/openkill` 作为 conffile 被保留时可能没有 `log_level` 字段，
  启动脚本读取到空值并生成空的 `log-level`，Mihomo 随即返回
  `invalid log-level`，配置校验失败后服务主动停止。核心文件、加载器和
  权限均正常；临时补回 `log_level=0` 后旧版立即能够启动，证明故障在
  配置迁移而不是核心缺失。
- 修复位于
  `luci-app-openkill/root/usr/share/openkill/openkill_config_normalize.sh`、
  `luci-app-openkill/root/etc/init.d/openkill` 和
  `scripts/test-uci-lifecycle.py`。安装/升级/重装归一化会为缺失或不支持的
  日志等级写入安全默认值 `0`；启动入口仍做防御性回退，避免旧 conffile
  再次把空值送入运行配置。节点、订阅、规则、YAML、自定义文件及 Naive
  独立目录不在清理范围内。
- 修复源提交为
  `2a5a210bcaa8fad6fabb65530188f839b6019239`。Development CI
  `36728501878` 通过
  (https://github.com/dinggood615/openkill/actions/runs/36728501878)。
  RC Build `36731034406` 通过
  (https://github.com/dinggood615/openkill/actions/runs/36731034406)，RC
  IPK 为 7,716,402 bytes，SHA256
  `3a2786003e07efbbc8e4276ec2ef21f557d10edc49108e164cab604916c0f7d8`。
  RC 审计未发现个人节点、凭据或测试机数据。
- 受保护设备备份建立在
  `/root/openkill-reinstall-backup-20260930220300`（目录 700、归档 600），
  `configs.tar.gz` SHA256 为
  `f2af3bf0421889337b58e664f49fbe0d5228264fd4b8ade8220b72134cf719ff`。
  重装前删除旧配置中的 `log_level`，候选包强制重装后安装脚本自动恢复为
  `0`；设备包状态为 `2026-1199`，服务为 `running`，实际核心进程存在，
  就绪日志包含 readiness passed，控制器返回 HTTP 200。候选包随后完成
  停止（inactive、核心退出）和再次启动（running、核心恢复、控制器 200）。
- 正式 Release 工作流 `36735178748` 通过
  (https://github.com/dinggood615/openkill/actions/runs/36735178748)。标签
  `v2026-1199-ipk` 指向上述源提交，正式 Release 为
  https://github.com/dinggood615/openkill/releases/tag/v2026-1199-ipk 。
  正式 IPK 为 7,911,241 bytes，SHA256
  `9b0cb25900a75acd2b4a62cfde50fec205a037e3bea1dc6956deec615e1fc56f`：
  https://github.com/dinggood615/openkill/releases/download/v2026-1199-ipk/luci-app-openkill_2026-1199_all.ipk 。
  包频道 `latest-ipk.json` 已同步同一版本、提交、URL 和哈希。
- 正式 IPK 已在授权设备通过 `opkg --force-reinstall` 完成真实替换；
  conffile 差异被保留为设备侧的 `openkill-opkg`，没有覆盖用户配置。正式
  包安装事务最终返回 0，随后再次完成停止/启动：服务 `running`、核心进程存在、就绪日志通过、
  控制器 HTTP 200。当前配置哈希为
  `ce418ab554c42256baa169ca788e5b2f04e1f8c3b4ef7a4a7c891912d94ef174`，
  `log_level=0`，Naive 数据目录仍为 700，节点文件数量和独立组件状态未被
  清理。
- 当前运行的 Mihomo SOCKS5 入口在正式包安装后仍可用；清除代理绕过环境后，
  通过该入口对两个 HTTPS 目标连续三轮均返回 HTTP 204/200、退出码 0。
  这证明本次重装没有破坏现有核心联网和用户策略。设备上的独立 Naive
  组件、节点和保护权限仍存在，但本轮对其远端探测连续返回 TLS/连接失败，
  同时直接 DNS 查询无结果；受控对照显示短暂停止 OpenKill 核心后，同一
  Naive SOCKS5 请求返回 HTTP 204，恢复核心后再次失败。抓到的上游连接
  使用了设备 DNS 返回的 Fake-IP，说明当前设备的透明分类/节点端点绕过仍
  未覆盖独立 Naive 节点；这属于独立 Naive 与现有 Fake-IP 接管策略的待修
  复项，不是本次重装核心缺失。不能把它宣称为本次代码已验证的 Naive 远端
  联网成功，也没有通过关闭校验或改成 DIRECT 掩盖失败。较早的内核 trap
  记录发生在本次正式包重装之前。
- 本地 `scripts/local-gate.sh`、UCI 生命周期回归（19 项）、Naive 集成契约、
  UI 契约（29 项）、浏览器契约和 OpenKill 门禁通过；修改后的 shell 通过
  WSL `sh -n`。Windows 环境直接运行 Linux/BusyBox 运行时测试、安装器脚本
  和核心二进制测试仍受 CRLF、路径转换和 Linux ELF 限制，不能替代 CI；精确
  提交的 Development/RC/Formal 门禁均已通过。当前 Chrome computer-use 会话
  两次超时，故本轮未新增视觉页面截图证据；此前 LuCI HTTP/CSRF 页面验收记录
  仍保留，未将浏览器不可见误报为本轮视觉通过。

## 2026-09-30 2026-1198 插件设置七页保存与应用正式验收

- 重新核对当前页面定义后，实际七个页签为：运行与服务
  (`basic`)、网络与分流 (`network`)、NaiveProxy 与服务
  (`naive_service`)、兼容与辅助 (`compatibility`)、规则与订阅
  (`rules`)、性能与稳定 (`stability`)、系统维护 (`advanced`)。
  覆写设置仍使用独立的 CBI 保存/应用路径，作为对照。
- 截图所示故障的实际根因不是七个控制器各自保存失败，而是 NaiveProxy
  导入弹窗嵌在 LuCI 的外层 CBI `<form>` 中，隐藏的空字段带有原生
  HTML5 `required`。浏览器在提交前直接阻止了外层 Save/Apply，LuCI
  控制器因此没有收到请求。修复位于
  `luci-app-openkill/luasrc/view/openkill/naive_compatibility.htm`：
  隐藏弹窗字段不再注册父表单的 `required`，弹窗真正提交时仍由
  `submitNode()` 做条件校验；会话、ACL、CSRF、CBI 校验和保存/应用
  语义均未放宽。
- 真实 LuCI 页面在正式包上逐页操作并刷新重读：七页的 Save 均返回
  HTTP 200，字段页的修改均可重读（`persisted=1`）；NaiveProxy 页的
  提交也返回 HTTP 200；七页 Apply 均返回 HTTP 302 并回到 OpenKill
  页面。系统维护页使用真实 CodeMirror 可见编辑器验证，未把隐藏同步
  `<textarea>` 当作可见输入。最终表单 `checkValidity=true`，无
  `pageerror`；唯一控制台 403 来自未登录入口的预期拒绝，不是设置页
  JavaScript 错误。测试后的临时值和自定义防火墙测试文件已删除。
- 页面真实请求由 `device_luci_pages.py` 记录（脚本位于工作区外，未进入
  仓库、包或发布附件）。设备身份为 Kwrt/OpenWrt 25.12-SNAPSHOT
  x86_64 VMware。Save/Apply 请求和桥接服务重载路径可用；当前设备未
  安装 OpenKill 核心，`/etc/init.d/openkill` 最终为 inactive，故核心
  进程重启后的运行态不能宣称通过。Naive 组件同样未在该设备安装可执行
  二进制或节点，Naive/Mihomo 实际联网属于 **未验证**，不是本次设置页
  修复失败。
- 写入前的受保护备份仍保留在设备
  `/root/openkill-settings-backup-20260930194800`（目录 700，归档 600），
  `configs.tar.gz` SHA256 为
  `c416e971fbac3f221c23fab5bc331d9d1f9b6b9fc37c8c25014a5e150de290dc`。
  `openkill` UCI 配置、既有默认策略及目录权限均已复核；设备节点目录
  700，敏感文件权限由安装后脚本保持为 600。源码、RC、正式 IPK 和发布
  元数据均未包含本次个人节点链接、账号或密码；GeoSite 中的同名公共域名
  字节在 2026-1197 基线中已存在，并非本次节点数据。
- 本地 `test-naiveproxy-ui-browser.py`、29 项 UI 合同测试和
  `scripts/local-gate.sh` 均通过。源提交
  `7347ad2ab324b5d647f6a390157b56db8403264d` 的 Development CI
  `36717000634` 通过
  (https://github.com/dinggood615/openkill/actions/runs/36717000634)。
  RC Build `36717204379` 通过
  (https://github.com/dinggood615/openkill/actions/runs/36717204379)，
  IPK 为 7,716,486 bytes，SHA256
  `936a6c1a51067816892af899c52288324b7cc14f724277cd765f6e1d4f1e73ee`。
- Formal Release `36722275576` 以 `release_gate=true`、`publish=true`
  通过
  (https://github.com/dinggood615/openkill/actions/runs/36722275576)。标签
  `v2026-1198-ipk` 指向上述源提交，正式 Release 为
  https://github.com/dinggood615/openkill/releases/tag/v2026-1198-ipk 。
  正式 IPK 为 7,910,459 bytes，SHA256
  `e6fafcd194c206b3038aeba7f28a523bf8b54dd84855215aedd0b4bbdd20d286`：
  https://github.com/dinggood615/openkill/releases/download/v2026-1198-ipk/luci-app-openkill_2026-1198_all.ipk 。
  包频道 `latest-ipk.json` 已同步 2026-1198、提交、URL 和同一正式哈希。
  正式包已在授权测试机用 `opkg --force-reinstall` 完成替换，安装状态为
  `luci-app-openkill 2026-1198`；同版本“已是最新”未被用作安装证据。

## 2026-09-30 2026-1197 listener ownership follow-up

- Follow-up review found that wildcard/IPv6 port collisions were safely
  rejected but the `ss` evidence path could label a foreign wildcard socket as
  merely unknown.  The ownership probe now matches any address family and
  returns `port-owned-by-other-process` when a foreign PID owns the port; a
  regression fixture covers this branch.  No credentials, node data or
  network-policy behavior changed.
- Local import, integration, standalone, POSIX and repository gate checks pass.
  Exact-commit Development CI `36706800729` passed
  (https://github.com/dinggood615/openkill/actions/runs/36706800729).  RC Build
  `36707010551` passed
  (https://github.com/dinggood615/openkill/actions/runs/36707010551); its IPK
  is 7,716,363 bytes with SHA256
  `1ef9d9978b56fe12e2c872167059869f0fd88cd4e8f0c7cbd901ff2c997cc072`.
  The RC audit found no personal node or credential data, and the formal
  package was independently scanned for the same content.
- Formal Release `36707912428` passed with `release_gate=true` and
  `publish=true`
  (https://github.com/dinggood615/openkill/actions/runs/36707912428).  Tag
  `v2026-1197-ipk` points to source commit
  `f030c1cc99c31b3e190d2a0fa5884ff3e997c09e`; the release is
  https://github.com/dinggood615/openkill/releases/tag/v2026-1197-ipk .  The
  formal IPK is 7,910,298 bytes with SHA256
  `e9b801bc9a2d82b09ea0c026427ea327c4c754f4f237ed309572b6852c7c82d4`:
  https://github.com/dinggood615/openkill/releases/download/v2026-1197-ipk/luci-app-openkill_2026-1197_all.ipk .
  RC and formal hashes are intentionally recorded separately.
- The formal IPK was uploaded and installed on the authorized x86_64 test
  device with `opkg --force-reinstall`; package version is `2026-1197`, and
  the installed standalone script hash matches the source hash
  `1dd63450f0dccabe1107ba3ca47cf1204148b1129b2ebc702460d4dd149c2d3a`.
  Authenticated LuCI HTTP controls returned successful `start`, `stop`,
  `start`, and `health` stages.  Final evidence is `state=running`,
  `listener_owner=verified`, `local_ready=1`, `health=available`,
  `reason=probe-ok`, generation 2, and no pending apply.  After the final
  stop/start cycle, three forced SOCKS5 rounds to two HTTPS targets returned
  HTTP 204 and 200 on every round; no proxy-bypass variables were present.
- The current Mihomo process loaded a protected temporary configuration through
  its authenticated API with a credential-free loopback SOCKS5 node, a
  dedicated selector, and a loopback mixed listener.  Three rounds through
  that listener returned HTTP 204 and 200, then the original runtime
  configuration was restored with HTTP 204 and the temporary file removed.
  Existing WAN, DNS, firewall, route, TUN and default proxy policy were not
  changed.  The device retained its existing independent test node as user
  data; no personal node data is in tracked source or either package.
- The Chrome automation inventory still exposes no usable tab, so visual
  browser/keyboard/narrow-viewport confirmation remains **unverified**.  The
  LuCI controller and CSRF-bound HTTP path were exercised against the real
  device; this record does not claim a screenshot-only browser pass.
- This acceptance record is committed as `8e3092c95d81b0703a575a8b238ee72b9d2f1e76`
  and its exact Development CI `36709376595` passed
  (https://github.com/dinggood615/openkill/actions/runs/36709376595).  The
  formal release intentionally remains sourced from the tested code commit
  `f030c1cc99c31b3e190d2a0fa5884ff3e997c09e`.

## 2026-09-30 2026-1196 Naive request-validation and read-only health follow-up

- Revalidated the prior 2026-1195 claims against the current worktree and
  authorized x86_64 test device.  The device still has the previously retained
  independent test node; it is not present in tracked source, default config,
  package content, or the new release note.  A protected pre-change backup is
  retained on the device at `/root/openkill-naive-backup-20260930174922` with
  mode 700; its contents are not copied into the repository or release.
- The screenshot's `request-validation` path is now addressed at its actual
  boundary: pasted links are trimmed before the browser submits them, and the
  controller applies the same trim to the `share` field before rejecting
  control characters.  Internal control characters and overlong fields remain
  rejected.  This change preserves credentials and does not bypass CSRF or
  LuCI ACL checks.  The current authenticated device HTTP probe previously
  reproduced successful import/duplicate handling, but the Chrome tab was not
  visible to the computer-use inventory during this run; visual browser
  confirmation remains unverified.
- Standalone health is now observational when a node has no applied runtime
  config: it reports `node-config-not-applied` and leaves both the config file
  and port map unchanged.  Port allocation is guarded by a bounded lock and
  atomically replaces a node's mapping; listener collision checks cover any
  address family/bind address instead of only 127.0.0.1.  The reboot-only
  component refresh changes only the two component evidence lines in an
  existing manifest.
- Candidate and formal package device evidence is complete: after the
  2026-1196 candidate install, the real LuCI HTTP flow imported the authorized
  link (`stage=accepted`), started and health-checked the node, stopped it
  (the PID and listener disappeared), started it again, retained the protected
  password during an edit, applied generation 2, and restored `pending_apply=0`.
  Three rounds through the SOCKS5 reached both HTTPS targets (204 and 200 with
  exit 0), and two instances ran concurrently; stopping the temporary instance
  left the original verified.  The same sequence was repeated after a
  `--force-reinstall` of the formal IPK.
- A temporary Mihomo config containing only a credential-free loopback SOCKS5
  proxy, a dedicated selector and a loopback mixed listener was loaded through
  the authenticated API both before and after formal installation.  Three
  rounds after each load returned 204 and 200 with exit 0.  The original
  runtime config was restored and temporary files removed.  No WAN, DNS,
  firewall, route, TUN or default proxy policy was changed.
- Local regression gates pass after the follow-up changes: standalone fixture,
  import behavior, integration contract, UI contract, POSIX syntax and the
  repository local gate.  Version authorities are synchronized at `2026-1196`.
  Exact-commit Development CI `36702993130` passed
  (https://github.com/dinggood615/openkill/actions/runs/36702993130); RC Build
  `36703169459` passed
  (https://github.com/dinggood615/openkill/actions/runs/36703169459).  The RC
  IPK is 7,716,341 bytes with SHA256
  `641109c7b77c4dc5f2357bb2243549ddc123dd0bd9c93819bbe9675974060828`.
- Formal Release `36704944101` passed with `release_gate=true` and `publish=true`
  (https://github.com/dinggood615/openkill/actions/runs/36704944101).  Tag
  `v2026-1196-ipk` points to `01d411914c810d2a8c38b38d26a4581b7d57c5d4` and
  the release is https://github.com/dinggood615/openkill/releases/tag/v2026-1196-ipk .
  The formal IPK is 7,909,931 bytes with SHA256
  `469e6b4337e961dab466daaf97b76c4928e6d24e7da87960cc95f0cb22c28b9e`:
  https://github.com/dinggood615/openkill/releases/download/v2026-1196-ipk/luci-app-openkill_2026-1196_all.ipk .
  RC and formal hashes are intentionally different and were recorded
  separately.  The formal IPK was force-reinstalled on the test device and
  its post-install LuCI/SOCKS5/Mihomo smoke checks passed.
- The Chrome tab was not exposed by the computer-use inventory during this
  run.  LuCI behavior was therefore verified through the authenticated HTTP
  requests and device evidence above, while visual Chrome/keyboard/narrow
  viewport confirmation remains **unverified** and is not claimed as passed.

## 2026-09-30 2026-1195 formal release and final device verification

- Rechecked the repository and preserved the existing device backups.  Source
  commit `8349ee5e6d7a80561e4c958f3d55b6d5486ce8a4` carries synchronized version
  `2026-1195`.  The real LuCI controller failure was reproduced and fixed: the
  current runtime requires string file modes (`0700`/`0600`), and the previous
  shell-pipe control path was replaced with a protected per-request file plus
  `/usr/bin/env` fork/exec.  Results now retain stage and exit evidence rather
  than reporting a generic controller rejection.
- The Naive bridge now uses incremental procd registration, waits only after
  the transaction is committed, clears inherited proxy variables, verifies PID
  to listener socket inode ownership, and keeps health checks read-only.  The
  UI separates import from edit password retention and distinguishes saved,
  starting, local-ready, remote-verified and Mihomo-unverified states.
- Exact-commit Development CI `36685134897` passed
  (https://github.com/dinggood615/openkill/actions/runs/36685134897).  RC Build
  `36685296384` passed
  (https://github.com/dinggood615/openkill/actions/runs/36685296384); its IPK is
  7,715,285 bytes with SHA256
  `5e8724c19e4c0d9271cc98bfcbc77b100a76717880583ee02985ff3d4f519786`.
  The RC audit found no personal node or credential data in source/package
  content.
- Formal Release `36685818942` passed with `release_gate=true` and
  `publish=true`:
  https://github.com/dinggood615/openkill/actions/runs/36685818942 .  Tag
  `v2026-1195-ipk` points to the expected source commit and the release is
  https://github.com/dinggood615/openkill/releases/tag/v2026-1195-ipk .  The
  formal IPK is 7,907,553 bytes, SHA256
  `150cce47a676dc56d9f9d427912be1e70004efa5f4ce8fa0363982b94503cd71`:
  https://github.com/dinggood615/openkill/releases/download/v2026-1195-ipk/luci-app-openkill_2026-1195_all.ipk .
  RC and formal hashes are intentionally recorded separately; the package
  channel reports `v2026-1195` and the published metadata carries the same
  formal URL and digest.
- On the authorized Kwrt/OpenWrt 25.12-SNAPSHOT x86_64 VMware device, the
  formal package was verified by SHA256 and installed with a completed,
  waited-for `opkg --force-reinstall` transaction.  Device status is
  `2026-1195`; package-owned files are `root:root` with expected modes.  The
  first interrupted SSH install was allowed to finish/roll back before the
  second install; no same-version “already latest” result was used as proof.
  A transient truncated `/etc/config/openkill` was restored from the protected
  pre-1195 backup before restarting the existing Mihomo service.  The retained
  backup is `/root/openkill-naive-backup-20260930154500/pre-1195-rc` (mode 700).
- The independent component is `v154.0.8037.49-2`; the authorized test node
  is generation 2, HTTPS, local port 11080.  Final manifest evidence is
  `component_status=available`, `state=running`, `listener_owner=verified`,
  `local_ready=1`, `health=available`, `reason=probe-ok`, and
  `pending_apply=0`.  Protected directories remain 700 and node/runtime
  files 600.  No new Naive SIGTRAP was observed after the formal installation;
  older kernel entries predate this final run.
- Real LuCI interaction on the same source was completed through import,
  save, save-and-start, stop, start, node test, retain-password edit and
  apply.  After the formal package install, the available Chrome session also
  completed stop -> start -> node test (`连接成功`).  The browser extension
  later disappeared from the automation inventory, so a final screenshot-only
  refresh after the service recovery is **unverified**; device-side status and
  health evidence remain available.
- Forced SOCKS5 requests cleared all proxy bypass variables and completed
  three rounds to two HTTPS targets with exit code 0 and HTTP 204/200 on every
  round.  Two independent instances on ports 11080/11081 ran concurrently;
  both passed the two targets, then node-2 was stopped and removed while
  node-1 stayed running and passed another request.
- The current running Mihomo process was restarted from the restored existing
  configuration without changing user YAML policy.  Its API selected the
  credential-free loopback node in the dedicated test group (HTTP 204), actual
  proxy requests returned HTTP 204 and 200, and the prior group selection was
  restored with HTTP 204.  Mihomo UI detection intentionally remains
  “未验证” when arbitrary user YAML/group ownership cannot be parsed reliably;
  the running-instance request itself is verified.
- Source/package audits found no personal node, hostname, username or
  credential in tracked source, RC content, formal content or default files.
  The node visible on the device is retained independent service data from the
  authorized test machine; it is not shipped by the project package.  Only
  task-created old duplicate backups were cleaned after the device reached
  100% overlay usage; the latest recovery backups were retained.
- Local gates passed: Naive import behavior, integration contract, UI browser
  contract, standalone fixture, POSIX syntax, WSL local gate and repository
  preflight.  No whole-device reboot was performed by the agent.

## 2026-09-30 2026-1194 formal release and post-reboot device acceptance

- The baseline was rechecked after the authorized test-machine reboot.  The
  source worktree was clean at `0f87c59700708ee0025019a984a388168063fbec`
  (`0f87c59`), with synchronized version `2026-1194`.  This release includes
  the request/result isolation and incremental procd lifecycle fixes, package
  ownership normalization, and the Fake-IP-safe Naive endpoint resolver rule.
  The resolver rule is generated only while preparing a runtime config; no
  device DNS, firewall, route or TUN setting is changed.
- Exact-commit Development CI run `36673066905` passed:
  https://github.com/dinggood615/openkill/actions/runs/36673066905 .  The exact
  commit RC Build run `36673312539` passed; its IPK is 7,714,289 bytes with
  SHA256
  `8308a69815a9e213aad0cf234f68793992265b885c006c55a4df9b5f6ea32351`.
  The RC package audit confirmed root ownership for the init/config/custom
  files and retained protected node-file permissions.
- Formal Release run `36674180379` passed with `release_gate=true` and
  `publish=true`:
  https://github.com/dinggood615/openkill/actions/runs/36674180379 .  Tag
  `v2026-1194-ipk` points to the expected source commit and the formal release
  is https://github.com/dinggood615/openkill/releases/tag/v2026-1194-ipk .  The
  published IPK is
  https://github.com/dinggood615/openkill/releases/download/v2026-1194-ipk/luci-app-openkill_2026-1194_all.ipk
  , 7,904,100 bytes, SHA256
  `234b2ae8f647e04b3e8fc79a099e2895eb30e1f460f1d56f182515229e4aba84`.
  RC and formal hashes are intentionally recorded separately.  The package
  channel is also live and consistent: `package/master/version` is `v2026-1194`
  and `package/master/latest-ipk.json` points to the same formal commit, URL and
  SHA256.
- The authorized device was reidentified as Kwrt/OpenWrt 25.12-SNAPSHOT,
  x86_64 VMware.  Before the formal replacement, a protected backup already
  existed at `/root/openkill-naive-backup-20260930135000/pre-1194-rc` (mode
  700 directory, mode 600 archives/config).  The formal IPK was copied over
  a protected channel, its device SHA256 matched the published hash, and
  `opkg install --force-reinstall` completed.  Device package status is
  `2026-1194`; the installed standalone script SHA256 matches the source and
  formal package.  The temporary `/tmp` package/backup files were removed
  after verification.
- Component evidence: official Naive executable `154.0.8037.49`, metadata
  release `v154.0.8037.49-2`, executable probe successful.  The authorized
  test node was re-read as generation 3, HTTPS transport, local
  port 11080.  The process PID, generated config and `127.0.0.1:11080`
  listener are tied to the same instance; manifest reports
  `listener_owner=verified`, `local_ready=1`, and health `available`/`probe-ok`.
  Runtime config contains the resolver mapping rule, while node/runtime
  directories and files remain 700/600.  Credentials were checked for
  persistence consistency without returning their values.
- Forced SOCKS5 tests cleared proxy bypass variables and completed three rounds
  to each of two HTTPS targets, returning HTTP 204 and HTTP 200 with exit code
  0 in every round.  A formal-package stop/start returned the listener and
  cleared stale health.  A retain-password edit/apply advanced generation 2
  to 3; after applying the new config, the same three-round/two-target SOCKS5
  test passed again.  A temporary second instance on 11081 ran concurrently,
  passed both HTTPS targets, and was stopped and removed; node-1 remained
  running and unaffected.
- Current running Mihomo was tested through its API and actual HTTP proxy.  The
  credential-free loopback node for the authorized test was selected in the dedicated
  `日本自动组`; gstatic returned 204 and Cloudflare trace returned 200.  The
  original top-level group `手动组` was restored with API status 204.  Source
  YAML, runtime group membership and the running process were checked; no
  whole-device traffic policy was changed.
- Local standalone/import/integration/POSIX/UI-contract tests and the WSL
  local-gate all pass.  The current CUA inventory exposes only the Codex
  in-app browser and not the user's Chrome tab, so post-reboot live LuCI
  browser import/CSRF/screenshot verification could not be re-observed in this
  session.  The backend request-file path, service lifecycle and UI contract
  tests are verified; this browser-session item remains **unverified**, not a
  claimed success.  No whole-device reboot was performed by the agent.

## 2026-09-30 2026-1192 release; device acceptance blocked during candidate upgrade

- Baseline was rechecked at source `04908019b970f7f68ad02a64ce77cde312442dce`.
  The worktree was clean before release work.  The repair chain is now:
  `71b0bf3` (legacy archive-vs-binary component digest), `375c256` (incremental
  per-node procd start), `466aaaf` (LuCI request/result isolation), and
  `0490801` (TLS-verified formal SDK downloads and synchronized version
  `2026-1192`).
- Exact-commit Development CI run `36667980688` passed.  RC Build run
  `36668086837` passed; the candidate artifact contained an IPK of 7,713,953
  bytes with SHA256
  `c2a7aeee5f6807a31b5175765cb4b4d8dd46c85ec3e991d641b4b77ce4df47cb`.
  The RC audit passed package metadata, conffile preservation, maintainer
  deletion safety, stale-reference and sensitive-content checks.
- Formal Release run `36668229527` passed with `release_gate=true` and
  `publish=true`.  Tag `v2026-1192-ipk` points to the expected source commit:
  https://github.com/dinggood615/openkill/releases/tag/v2026-1192-ipk .  The
  formal IPK is 7,933,671 bytes with SHA256
  `7b43d6f83be805b77ea3e9710325929adefe60fa5852094f3d521888dc771ba1`.
  The package channel `package/master/version` reports `v2026-1192`, and
  `package/master/latest-ipk.json` matches the formal tag, source commit and
  digest.  RC and formal hashes are intentionally recorded separately.
- The authorized device identity was previously confirmed as Kwrt/OpenWrt
  25.12-SNAPSHOT x86_64 VMware.  Protected backups exist at
  `/root/openkill-naive-backup-20260929185837` and the task-created
  `pre-1189`, `pre-1190` and `pre-1191` roots under timestamped directories;
  Naive directories were mode 700 and sensitive files mode 600.  Candidate
  2026-1190 was installed and the real node/component data remained present.
- The authenticated Chrome LuCI session was reused.  The real node had been
  imported and persisted before this release iteration.  With candidate
  2026-1190, LuCI stop worked, but LuCI start still produced
  `service-start-failed`; device logs showed the official Naive process
  trapping immediately when launched through the uWSGI `io.popen` pipe.  The
  same node started and held a verified loopback listener when invoked through
  the request-file/SSH path.  This reproduced the remaining LuCI transport
  defect and motivated 2026-1191.
- Candidate 2026-1191 was then copied and its `opkg install` entered the
  package post-install OpenKill restart, but the device stopped answering SSH
  and LuCI during that restart.  The installation command was interrupted
  after a bounded wait; package completion, final installed version, formal
  2026-1192 installation and post-upgrade smoke are therefore **not
  verified**.  No whole-device reboot was performed (not authorized).
- Before the device became unreachable, the upstream Naive endpoint had also
  shown TCP/SOCKS timeouts while direct WAN access remained available.  This
  is retained as an external remote-node blocker, not reclassified as an
  authentication success or a DIRECT fallback.  Current device process,
  SOCKS5, three-round HTTPS and running Mihomo-group results cannot be freshly
  collected until the authorized device responds again.
- Correction to the older 2026-1180 section below: its statement that a
  same-version formal package was installed is not sufficient evidence when
  `opkg` reported “already up to date”.  Treat that historical installation as
  **not independently replacement-verified**; the package channel and formal
  release metadata above are the current verified publication evidence.

## 2026-09-29 2026-1180 formal release and authorized device acceptance

- Baseline was rechecked at source `95a3d0d362e7be78e35219de2ebb79048b47781b`.
  The follow-up commit `1ed36e0ecf50dc33cca64d752dc977dbd8153b69` adds
  `/etc/openkill/custom/openkill_custom_overwrite.sh` to the opkg conffiles,
  bumps the synchronized version to `2026-1180`, and adds a contract test.
  This fixes a release-only regression where an upgrade replaced a user's
  Mihomo custom overwrite hook and removed the manual loopback listener.
- Exact-commit Development CI run `36579416565` passed. RC Build run
  `36579730489` passed; its IPK was 7,712,717 bytes with SHA256
  `841e38cd025303afb7dae1b52cedf229a571486b9ccb0ff6e42f31247f6bc7a4`.
  The RC audit verified package metadata, both conffiles, maintainer-script
  deletion safety, stale development references and sensitive/test content.
- Formal Release run `36580520637` passed with `release_gate=true` and
  `publish=true`. Tag `v2026-1180-ipk` points to the 1ed36e0 source commit;
  release: https://github.com/dinggood615/openkill/releases/tag/v2026-1180-ipk
  The formal IPK is 7,930,222 bytes with SHA256
  `e541adf20aef8281df926a5d3374e096011dd83c605705319bed7ce98a4231f3`.
  The package channel reports `v2026-1180`.
- A previous run recorded package status `2026-1180` on the authorized
  `192.168.1.103` OpenWrt/Kwrt 25.12-SNAPSHOT x86_64 VMware test machine, but
  the installation command for the same version reported “already up to date”.
  That result does not prove that the formal bytes replaced the installed
  package; formal-package replacement is consequently **not independently
  verified**.  The component version and device evidence below remain useful
  runtime history only.
  The protected backup root is `/root/openkill-naive-backup-20260929185837`
  (mode 700; `pre-1179`, `pre-1180` and `pre-formal-1180` snapshots are mode
  700 with protected files). Node directory/file and generated runtime config
  permissions are 700/600. The custom overwrite conffile remained present
  after the formal package installation, and the dedicated Mihomo listener
  remained on loopback.
- Device acceptance passed for the real supplied node without printing its
  credentials: node generation 5 is running, the PID-to-listener ownership is
  verified, health is `available`/`probe-ok`, and the independent SOCKS5
  endpoint returned HTTP 204 from gstatic and 200 from Cloudflare in three
  rounds each. Stop/start cleared stale health and restored the listener.
  A retain-password edit/apply advanced generation 4 to 5 and revalidated the
  same request. A temporary second node proved both 11080/11081 instances
  could run concurrently; stopping node-2 left node-1 running and reachable.
- The current running Mihomo instance retained the credential-free
  `127.0.0.1:17891` test listener and its dedicated group after the formal
  package install. Three rounds to the same two HTTPS targets returned 204/200
  through that listener. Existing default policy was not changed; no WAN,
  DNS, firewall, route, TUN, other-plugin or remote-VPS setting was changed.
- Automated standalone, integration, import, POSIX and local-gate tests pass;
  Development CI, RC and Formal Release all pass on the exact source commits.
  The supplied LuCI login was attempted twice and rejected by the device as an
  invalid username/password. Therefore authenticated LuCI import/CSRF/browser
  acceptance remains an explicit external authentication blocker; the backend,
  device lifecycle, SOCKS5 and current Mihomo path are not represented as a
  successful LuCI page submission.

## 2026-09-29 Candidate multi-instance follow-up

- Candidate 2026-1178 was installed and exposed a second real lifecycle defect:
  targeted `start_node node-2` used procd's default `set` operation and
  replaced the existing instance table, stopping node-1. The source now uses
  `procd_close_service add` for targeted starts while full service start/reload
  retains the complete `set` transaction.
- The temporary node-2 was removed after the reproduction. The device's
  node-1 was restarted and independently verified through its SOCKS5; the
  current Mihomo loopback listener continued to return successful HTTPS
  responses. This candidate was superseded by the 2026-1180 release after the
  conffile-preservation regression was found and fixed.
- Local standalone, integration, import, POSIX and local-gate tests pass for
  the targeted procd change. Version 2026-1178 is not a release candidate for
  publication because this additional source fix supersedes it.

## 2026-09-29 NaiveProxy lifecycle follow-up and current Mihomo test entry

- Rechecked baseline at source HEAD `c4a1ad7f228064b53651db5e25375cca42124552`.
  The authorized device remains OpenWrt 25.12-SNAPSHOT x86_64 VMware with
  formal package 2026-1177 installed. Existing node, component and protected
  backup were preserved.
- A device stop/start reproduction found a real remaining defect: the old
  `health.node-1` file survived `stop_node`, so the manifest could expose an
  expired result from the previous process generation. The bridge now clears
  health state on every new start attempt, failed readiness, targeted stop and
  service stop/reload. This is the 2026-1178 source change.
- The formal-package install warning `yml_change.sh: ... use: command not
  found` was traced to backticks in an embedded Ruby comment inside a shell
  double-quoted Ruby program. The comment is now shell-safe. Package-owned
  runtime/UI files are normalized to `root:root` by postinst; protected Naive
  node and state paths remain 700/600.
- Device-only Mihomo evidence: the selected `/etc/openkill/openkill.optimized.yaml`
  was backed up under `/root/openkill-naive-backup-20260929185837`, then given
  a credential-free authorized-test loopback proxy group and a dedicated
  `127.0.0.1:17891` mixed listener. Mihomo API reload returned HTTP 204,
  the listener belonged to the running clash process, and three rounds to two
  HTTPS targets returned 204/200. The default proxy group was not changed.
  A custom overwrite hook preserves this test entry across OpenKill config
  regeneration; no WAN, DNS, firewall, route, TUN or other-plugin setting was
  changed.
- After targeted stop/start, the Naive listener disappeared and returned;
  the independent SOCKS5 request and the current Mihomo test listener both
  succeeded. The pre-fix stale health timestamp remains historical evidence;
  the new package must be installed before claiming the cleanup fix on-device.
- Local WSL tests pass: standalone fixture, integration contract, import
  behavior, POSIX syntax and `scripts/local-gate.sh`. A Windows browser login
  was attempted twice with the credentials supplied in this session and the
  LuCI page rejected them as invalid; therefore authenticated LuCI import,
  CSRF/UI acceptance and credential-bearing page screenshots remain an
  external authentication blocker, not an unverified success.
- The remaining UI item is still conditional on a valid LuCI session: do not
  claim complete browser acceptance unless the device accepts valid credentials
  without changing the login configuration.

## 2026-09-29 NaiveProxy test-machine lifecycle and real-node verification

- Baseline was rechecked on the authorized `192.168.1.103` OpenWrt x86_64
  VMware test machine: installed OpenKill was `2026-1175`, and the saved
  node's server hash and non-secret fields matched the supplied test link.
  A protected backup was created at
  `/root/openkill-naive-backup-20260929185837` with mode-700 directory and
  mode-600 archive.
- Root cause evidence: the old bridge started Naive as `root:nogroup`; it
  accepted a SOCKS5 listener but could not establish upstream HTTPS. The same
  official binary and generated configuration as `root:root` returned HTTP
  204 and 200 through two independent HTTPS targets. The old readiness wait
  also ran before `procd_close_service`, so the process could appear later
  without an instance state file. Health previously regenerated the active
  runtime config; that is now avoided when the generated config is valid.
- Fixes are in commits `3dc247234cda9b9b83e185de307b7141c1504fba` and
  `dbc996ee6f3301f9af66affd960a52366b376f59`: preserve valid runtime config,
  register `start_node`/`stop_node`/`health`, use the real procd service and
  instance names, wait in `service_started` after transaction commit, record
  per-instance generation state, skip disabled nodes, and run with group
  `root`.
- Device evidence after source deployment: normal start returned success,
  instance state recorded generation 4 with `pending_apply=0`, listener
  ownership was verified, health was `available` with `probe-ok`, and both
  gstatic generate_204 and Cloudflare trace returned success through the
  loopback SOCKS5. A targeted stop followed by `start_node` returned success
  and the same HTTPS request succeeded again. A temporary Mihomo config passed
  `-t` and routed both targets through the loopback SOCKS5, then its test
  process was stopped and temporary files removed. No WAN, DNS, firewall,
  route, TUN, other-plugin or VPS changes were made.
- Local import, standalone, integration, POSIX syntax and local policy gates
  pass. The LuCI browser bridge opened the device title but timed out while
  returning accessibility/screenshot state; production-template UI tests
  remain the available UI evidence. The device currently has the repaired
  source files deployed temporarily, not a package built from the new
  release commit.
- Release delivery completed: source commit `f8c6d3c3a910410333c8879730a138c966431f3f`
  passed exact-commit Development CI run `36561263200`; RC Build run
  `36562702967` passed and produced the candidate IPK SHA256
  `93c4709ed9cb60b6b69d30450b2df50f0dc37341d4cafccf24acb0c200978f83`;
  Formal Release run `36563177410` passed with `release_gate` and `publish`
  enabled. Tag `v2026-1177-ipk` points to the same source commit, and the
  published IPK is 7,930,313 bytes with SHA256
  `36c59e3d2c5bda3fe21229c6ddd785252ac21c036e0611f588cbe490d9c2501a`.
  The formal package was installed on the authorized test machine and passed
  the same start, listener, health, and two-target HTTPS smoke checks. The
  protected backup remains available for recovery. The only uncompleted UI
  evidence is the live LuCI import submission: the authenticated Chrome tab
  reaches the device login form, but no LuCI password was supplied in this
  session, so no login or credential-bearing import submission was attempted.
  Production-template UI tests and backend/device control paths passed.

## 2026-09-29 NaiveProxy independent lifecycle, import and UI repair

- Scope: repair the independent NaiveProxy lifecycle and share-link contract,
  expose real listener/port evidence, and clarify the LuCI component-to-
  Mihomo hand-off. OpenKill UCI, DNS, firewall, route and TUN behavior remain
  outside this iteration.
- Changes: imported HTTPS/QUIC links now default an omitted port to 443,
  preserve literal `+` in URI credentials, reject ambiguous unbracketed IPv6,
  and allocate new ports only when they are absent from both the persistent
  map and the live listener table. The redacted manifest records transport and
  listener ownership; external listeners are surfaced as `conflict` and are
  never treated as a healthy Naive listener.
- The bridge now waits for a matching generated configuration, process and
  loopback listener after procd accepts a start request. Health checks report
  `port-owned-by-other-process` when listener evidence identifies another
  process. The LuCI card now shows the component-to-Mihomo flow, transport,
  process/listener state, explicit port conflicts and separate unverified
  Mihomo integration state.
- Local evidence so far: `test-naiveproxy-import.js`,
  `test-naiveproxy-standalone.py`, `test-naiveproxy-integration.py`, POSIX
  syntax checks and `sh scripts/local-gate.sh` pass. The standalone fixture
  covers omitted 443 and literal plus credentials. Windows browser execution
  is environment-dependent; no router write, service action, packet-path or
  authenticated remote endpoint test was performed.
- Release work: source and installer version were advanced from `2026-1175`
  to `2026-1176` with release notes in `docs/release/notes/2026-1176.md`.
  The versioned local gate passes and the bounded change is committed locally
  as `2d7d26af15e9f30ec0021e12d6ea01f7604aa230`. Push attempts from Windows
  Git and WSL both fail before authentication with a GitHub TLS handshake
  error (`schannel: failed to receive handshake` / `GnuTLS: handshake failed`).
  Development CI, RC Build and Formal Release therefore remain pending until
  GitHub transport is reachable; no release tag or artifact digest is claimed.

## 2026-09-27 NaiveProxy component, node persistence and edit repair

- Scope: repair the independent NaiveProxy control contract only: component
  diagnostics and installation/update actions, share-link import and
  persistence, protected node editing, per-node start/health state, and the
  matching LuCI card. OpenKill UCI, selected Mihomo YAML, proxy groups, DNS,
  firewall, WAN and route behaviour remain outside this change.
- Evidence baseline: the previous read-only device inspection found version
  `2026-1169` without `/etc/naiveproxy/naive`, no standalone node JSON and no
  NaiveProxy instance. The occupied `127.0.0.1:11080` listener belonged to a
  different process. A prior dialog failure was caused by invalid nested CBI
  form markup; the current source has the repaired form-like dialog but still
  lacks an edit operation, manual component detection/install controls and
  action-stage diagnostics.
- Local work will prove each bridge stage with fixtures and browser tests.
  A user-authorized, read-only device diagnostic phase is permitted for
  `192.168.1.103`: inspect the independently installed component, node files,
  service state, listener ownership and redacted logs only. It must not write
  configuration, install packages, start or stop services, alter WAN, DNS,
  firewall, routes, CENTRAL_ACTIVE or packet paths. All test links and
  credentials are fictional.
- Device diagnostic result: on 2026-09-27 the first attempts failed because
  the Windows password environment was not forwarded into WSL, not because of
  a proven router credential failure. The corrected read-only probe found an
  executable component with a successful version-probe exit, one mode-600
  enabled node file, a matching port-map entry and the bridge init script.
  The service reports active with no instances: there are no generated runtime
  config or instance-state files, no NaiveProxy process, no procd instance and
  no NaiveProxy loopback listener. This proves the node has not reached its
  start phase; it does not prove a remote connection failure. No router state,
  configuration, service, package or network setting was changed. Resume with
  an explicitly authorized start action only after preserving this baseline.
- LuCI import diagnostic: the installed 2026-1174 controller and view contain
  the independent-control route, but this LuCI generation adds its session
  token to normal POST helpers. The NaiveProxy view used `fetch` directly and
  omitted that token, so the dispatcher returned an HTML login/error response
  which the page correctly labelled `controller-html-response`. The bounded
  fix appends `L.env.token` to the form body when available. Its production
  template Playwright test now rejects a missing token and passes import and
  protected edit with the token present. Device deployment is deferred.
- Rollback: revert the bounded source commits. The component installer retains
  the previous executable, and node changes use mode-600 atomic files under
  `/etc/naiveproxy/nodes`; no OpenKill UCI or user YAML is touched.
- Local evidence: the standalone fixture now covers HTTPS and QUIC import,
  duplicate rejection, protected read, password retention, configuration
  generation conflict and atomic persistence. The component fixture confirms
  failed replacements retain the prior binary. The production-template
  Playwright card test covers link-first import, save, protected edit and
  narrow layout without horizontal overflow; the generic UI browser test also
  passes. `test-naiveproxy-import.js`, integration/runtime/UI contracts,
  POSIX syntax and `sh scripts/local-gate.sh` pass. No device, router or VPS
  action was performed under the repository boundary.
- Delivery evidence: implementation commit `771adfda732be69e3204e2257f1a35b3f6814a05`
  passed Development CI (run `36322321076`). Release source
  `f6f1c5fd5165e4e4640d46be328dc6e2631318a0` passed its exact Development
  CI (run `36322491754`), then RC Build and Formal Release. The published
  `v2026-1174-ipk` tag resolves to that release source. Its IPK SHA256 is
  `6dfef90c307251e4e62c7ad281a8f931349e1028e7db0eead3f7e32b40fcdadd`.
  The RC candidate SHA256 was
  `42721f7e68e93bc6dd4947e8159725d73956e5ced9005601d6e850aaf698bf01`.
  Release delivery does not add device, router, component-install, PID,
  listener or VPS evidence; those remain deferred by the repository guide.

## 2026-09-27 OpenKill UI theme toggle and light/dark consistency

- This iteration is limited to OpenKill-scoped presentation: the runtime
  status theme control, light/dark token handoff, card/control contrast and
  responsive layout. CBI field names, UCI values, controller routes, DOM
  events, validation, save/apply semantics, network/DNS/proxy behaviour and
  user configuration remain unchanged.
- The runtime status theme button keeps the existing `oc-theme` preference
  key and applies an explicit page-scoped `light` or `dark` mode. The host
  LuCI theme remains untouched; OpenKill's page root receives the resolved
  mode so stale host `data-theme` markers cannot override an explicit choice.
  Auto detection remains the initial fallback for existing users, while a
  button click chooses the opposite visible mode.
- CSS changes are restricted to OpenKill routes and use the existing
  `oc.css` -> `flat.css` load order. Terminal token rules will provide
  readable page, card, input, border, text, link, focus and state colours in
  both modes without changing layout semantics or adding network behaviour.
- Validation is local and browser-only in this iteration. Use the production
  status template/CSS preview, test the button and persistence in Chromium,
  cover desktop and narrow viewports, then run UI tests, POSIX/BusyBox checks,
  `sh scripts/local-gate.sh` and `git diff --check`. Device and VPS checks
  remain outside this plan. Rollback is the bounded source commit.
- Implementation and evidence: the status control now switches directly
  between explicit light and dark preferences while preserving the existing
  `auto` fallback for users who already have it stored. The resolved mode is
  mirrored to page-scoped `data-openkill-theme` markers and the final
  OpenKill CSS layer supplies both theme token sets without changing host
  LuCI markers. Real Chromium validation used the production preview at
  1920, 1366, 768 and 390 CSS px; all four sizes had no horizontal overflow,
  the toggle persisted `light`/`dark`, and console, page-error and external
  request checks were clean. Screenshots and JSON evidence are under
  `artifacts/test-evidence/ui-preview/`. UI contract, preview, interaction,
  browser and local-gate checks passed. No device or VPS evidence is claimed.

## 2026-1170 UI theme bridge and official NaiveProxy installer (2026-09-27)

- Scope for this iteration is limited to OpenKill-scoped visual adaptation and
  the one-click installer’s independent NaiveProxy component discovery,
  verification and rollback. CBI field names, UCI values, controller routes,
  DOM handlers, validation, save/apply semantics, DNS, proxy policy and
  network writers remain unchanged.
- The UI baseline uses the existing `oc.css` → `flat.css` load order. The new
  theme layer must consume available LuCI theme variables first, keep scoped
  light/dark fallbacks, preserve content-sized cards and avoid affecting LuCI
  system pages or other plugins. Browser evidence must record the actual theme,
  CSS viewport, DPR, zoom, computed colors and overflow; static CSS checks are
  not rendered evidence.
- The installer contract is: OpenKill package → independent-component
  preflight → official stable release metadata (API or a checked-in official
  catalog fallback) → HTTPS/size/SHA256/archive/ELF/loader/version checks →
  staged atomic replacement → separate component result. A missing or
  untrusted match is a named failure and never a guessed asset. Existing
  `/etc/naiveproxy/naive`, node JSON and runtime state remain intact on failure.
  Manual IPK installation does not silently claim that the external binary was
  installed; the page and installer distinguish management files from the
  official executable.
- The official release metadata reviewed for the fallback catalog is
  `klzgrad/naiveproxy` `v154.0.8037.49-2`; each catalog row is tied to its
  public release asset, size, SHA256 digest and OpenWrt target. The catalog is
  only a verified fallback when the bounded API lookup is unavailable; a fresh
  API result still wins.
- Device writes remain outside this iteration: the current plan permits only
  the previously recorded read-only device/browser checks and forbids package
  installation, service actions, packet-path tests, CENTRAL_ACTIVE, central
  nft, WAN/default-route/DNS changes and VPS authentication. Local fixtures,
  final CSS/browser preview and exact-commit CI are the required evidence.
- Rollback: revert the bounded source commit; for a device later authorized,
  preserve `/etc/naiveproxy` and `/var/run/naiveproxy`, restore the previous
  OpenKill package, and remove only the new installer/catalog files. No user
  YAML, subscription or node credentials are touched by this scope.
- Local evidence so far: the official catalog fallback resolves the checked
  `x86_64` asset without `jsonfilter`, while exact package architectures skip
  `all/noarch` and reject a machine/package mismatch. Installer, standalone
  bridge, integration, UI contract, UI preview, UI interaction, optimization,
  import behavior and POSIX syntax fixtures pass; `sh scripts/local-gate.sh`
  and `git diff --check` pass. The browser evidence uses production templates
  and CSS in Chrome, records 1920/1366/768/390 CSS px with no horizontal
  overflow, and captures distinct light/dark computed surfaces and text.
- The Windows host lacks PyYAML for the direct installer test; the same test
  passes in the repository's WSL environment. The browser fixture is local and
  uses a mock backend only. No device write or real VPS probe was run because
  this plan's device phase remains read-only/local-only.
- Implementation baseline commit `173d24ffa1625f359eeb3a48807ffc89dfa1bf49`
  was pushed to `master`; its exact Development CI run
  `36300769551` completed successfully at
  `https://github.com/dinggood615/openkill/actions/runs/36300769551`.
- The next release commit will advance the synchronized source version once to
  `2026-1170`, add reviewed release notes, and then use the manual RC and
  Formal Release gates. The release remains local/browser verified only for
  this iteration; device installation and real VPS connectivity remain pending.

## Authorized read-only NaiveProxy device diagnosis (2026-09-27)

- The user requested diagnosis on the existing test target `192.168.1.103`.
  This phase is limited to read-only inspection of the installed OpenKill and
  standalone NaiveProxy implementation: package/version inventory, init and
  component metadata, redacted manifest and health state, process/listener
  ownership, service logs, and import error stages.
- The phase must not start, stop, reload or install any service, read or print
  node credentials/share links, change UCI/YAML, touch WAN/DNS/firewall,
  enable `CENTRAL_ACTIVE`, apply central nft state, run packet-path traffic,
  or authenticate to a VPS. Any command output must redact secrets before it
  is retained.
- Resume evidence: exact installed package/source version, component probe,
  service/init status, sanitized process/listener evidence, sanitized import
  result, and a clear split between device-observed root causes and local-only
  fixes. If a write or service action is required, stop and request a separate
  authorized device phase.

### Read-only findings and local repair (2026-09-27)

- The target is running `luci-app-openkill` `2026-1169` on Kwrt/OpenWrt
  x86/64. The standalone component probe found no executable at the managed
  path (and no legacy fallback binary), so `naiveproxy-bridge` reports active
  with no instances. No standalone node JSON or generated instance config is
  present; therefore no NaiveProxy process could have started. The observed
  `127.0.0.1:11080` listener belongs to another process and is not evidence of
  a NaiveProxy instance.
- Browser reproduction on the authenticated settings page showed the import
  dialog, followed by `openDialog ... form.reset` with a null form. The CBI
  page already supplies an outer form, so the nested `<form>` in the Naive
  template is discarded by HTML parsing. This prevented both share-link
  parsing and node persistence before the backend could receive an import.
- The local repair removes the nested form, uses a form-like group with
  explicit save/save-and-start handlers, clears sensitive fields when the
  dialog closes, and keeps the outer CBI form untouched. The standalone
  backend and control route remain unchanged; no device files, UCI, YAML,
  service state or network settings were written during this diagnosis.
- Local evidence: `scripts/test-naiveproxy-integration.py` passes and the
  standalone fixture passes. The test device still needs a separately
  installed compatible official NaiveProxy component and the resulting IPK
  before import/start can be re-tested; that write phase is outside this
  read-only authorization.

## Authorized Playwright test-device phase (2026-09-27)

- Authorization: the user explicitly approved continuing the Playwright and
  test-device validation phase after the local browser fallback was verified.
  The scope is limited to the existing OpenWrt target `192.168.1.103` and its
  OpenKill LuCI page, using the already configured read-only SSH access.
- Allowed: inspect the device's available runtime, install only the minimum
  browser-test tooling if technically viable, serve or access the OpenKill UI,
  and run read-only DOM/layout/accessibility checks.  Any temporary package or
  cache must be recorded and removable without touching OpenKill user data.
- Forbidden: CENTRAL_ACTIVE, central nft apply, packet-path or traffic tests,
  WAN/default-gateway/DNS policy changes, OpenKill/Mihomo/Naive service
  restarts, user configuration writes, credentials in commands/logs, and any
  remote VPS authentication.  If the device cannot host a browser runtime,
  use local Playwright against a read-only device UI endpoint and record that
  split explicitly.
- Rollback: remove only the test tooling/cache installed for this phase and
  restore any temporary port-forward/process; do not remove packages or files
  that predated this phase.  No package or service mutation is performed until
  a read-only capability check identifies the exact target paths and space.
- Resume evidence required: device capability inventory, browser/Playwright
  execution result, viewport and overflow measurements, console/network error
  report, and a clear list of checks not possible without packet-path or
  authenticated UI access.

## Playwright local browser validation (2026-09-27)

- Local capability: installed Python Playwright 1.63.0 and its Chromium
  browser under the user environment.  The bundled browser executable returned
  Windows `spawn UNKNOWN`, so `scripts/test-ui-browser.py` now tries the
  installed Playwright browser first and then verified local Chrome/Edge
  executables.  No production page, network setting or device configuration
  is changed by this fallback.
- Local result: UI contract (28 tests), preview (2), interaction (1), browser
  validation and `sh scripts/local-gate.sh` passed.  The browser suite reports
  `UI_BROWSER=PASS`, `UI_PRODUCTION_JS=PASS`, `UI_DIMENSIONS=4/4` and
  `UI_LOCAL_REQUESTS=PASS`; it exercised 1920, 1366, 768 and 390 CSS-pixel
  viewports and wrote screenshots/evidence only under the ignored
  `artifacts/test-evidence/ui-preview/` directory.  The run used local Chrome
  after the bundled executable failed to spawn.
- Test-device read-only preflight: the authorized OpenWrt target reports
  x86/64, has no `python3`, Playwright module or Chromium/Chrome executable.
  The current approved device phase explicitly forbids package installation,
  service restart and packet-path testing, so Playwright cannot be deployed or
  run there in this iteration.  No device state was changed.
- Gate: a separate device plan must explicitly authorize installing the
  required runtime/browser (or provide an existing supported browser), define
  its storage and rollback scope, and permit the requested OpenKill UI test.
  Until then, device browser validation remains `REAL_DEVICE_GATE` and remote
  Naive/VPS behavior remains unverified.

### Authorized phase result

- Read-only capability checks reached `192.168.1.103` over the configured SSH
  key and HTTP.  The target is Kwrt/OpenWrt x86/64 with `opkg`, about 624 MB
  free overlay and no installed Python, Node, Playwright, Chromium, Chrome or
  Firefox.  Cached package metadata exposes no directly installable browser or
  Playwright package, so device-side deployment is not technically viable
  without introducing a large external runtime and its dependencies.
- Local Playwright/Chrome opened the device LuCI endpoint at 1366 x 900 CSS px
  (DPR 1), confirmed the LuCI login page rendered with no horizontal overflow,
  and saved the read-only screenshot to
  `D:\openkill-cache\device-ui-20260927.png`.  No credentials were entered and
  no device configuration, package, service, route, DNS, firewall or packet
  path was changed.
- The device UI stopped at the LuCI login screen.  OpenKill page rendering,
  authenticated CBI interactions and device-side browser execution require a
  temporary LuCI test account/session or an existing browser runtime.  Those
  remain unverified; the local preview and local Playwright suite are the
  authoritative results for this iteration.
- Follow-up with the user-provided temporary LuCI credentials succeeded
  without storing them.  The authenticated target still returns LuCI 404 for
  `/admin/services/openkill/settings`; read-only SSH checks show no installed
  `luci-app-openkill`, no `/etc/config/openkill`, and only a residual
  `/usr/share/openkill` directory.  The device OpenKill UI therefore cannot
  be exercised until a current test IPK is explicitly authorized for
  installation.  No package, service, configuration, route, DNS, firewall or
  packet-path mutation was made.

## Authorized current test-IPK installation (2026-09-27)

- The user explicitly authorized installing the current source test IPK on the
  existing test target `192.168.1.103`. This is a package-installation test,
  not authorization for packet-path, WAN, DNS, firewall, CENTRAL_ACTIVE,
  central nft, Mihomo, NaiveProxy, or VPS tests.
- Before mutation, record the installed-package list, relevant OpenKill paths,
  free space and the package control scripts. Transfer only the IPK built from
  the exact source commit under test. Install only `luci-app-openkill`; do not
  install unrelated dependencies or browser runtimes and do not invoke service
  start/restart commands. Preserve any pre-existing `/etc/config/openkill`,
  `/usr/share/openkill`, user YAML and independent-service data.
- The rollback record must include the pre-install inventory, package SHA256,
  install result and a reversible `opkg remove`/previous-package restore path.
  Any package-created defaults are test state and must be reported separately
  from user data; no credentials may enter logs or evidence.
- After installation, use local Playwright/Chrome only for authenticated,
  read-only LuCI DOM/layout/accessibility checks at the authorized target.
  Do not click OpenKill save/apply, service, network or configuration actions.

## Whole-repository simplification audit (2026-09-27)

- The user requested a new end-to-end review of the OpenKill source and
  removal of unnecessary project content. This supersedes the in-progress
  test-IPK build, which was stopped before an IPK was produced.
- Scope: map tracked files to source imports, LuCI routes/templates, packaging
  manifests, install scripts, workflows and tests; remove only material that
  has no live runtime, packaging, upgrade, documentation or test purpose.
  Preserve user configuration, compatibility/upgrade paths, release evidence,
  license notices and unknown working-tree changes.
- Method: first produce a reference inventory and identify candidates with
  evidence. Each deletion must have an explicit replacement or a zero-reference
  result, with focused tests and package-manifest checks. Do not remove content
  merely because it appears old or is not exercised by one UI page.
- Boundaries: local repository work only. No device package installation,
  service action, network, DNS, firewall, CENTRAL_ACTIVE, central nft,
  packet-path or VPS operation is part of this audit.
- First verified removal batch: the build recipe already excluded the checked-in
  Zashboard bundle while the runtime downloader fetches it on demand. Removed
  those 21 source-only assets and the now-redundant build-time deletion. Also
  removed five root-level images with no source, documentation, installer or
  package reference. The removed tracked content totals 26 files and
  6,048,491 bytes. MetaCubeXD, dashboard routes and the Zashboard downloader
  remain intact.
- Validation: `test-openkill-optimization.py`, `test-ui-contract.py`,
  `test-ui-preview.py`, POSIX shell syntax checks, `local-gate.sh` and both
  staged/unstaged `git diff --check` passed. Next candidates require separate
  evidence: legacy CSS that is currently pruned only during packaging, and
  unused controller/template pairs. Do not remove them until their references
  and final-package behavior are independently verified.
- Second verified removal batch: the first-release source stylesheet contained
  1,019 lines that the package recipe deterministically removed on every
  build. Applied that same transform to the source, removed the redundant
  `prune-ui-css.sh` build helper, and changed the validation gate to reject
  retired OixCloud styling directly in the shipped stylesheet. The transformed
  stylesheet has the exact SHA256 produced by the prior package-time transform
  (`7de52948ce987ee3884dc0048f794350fac9013183ed49ae40a8d20c8f3ac192`),
  so this does not alter the delivered CSS semantics.
- Second-batch validation: the local policy gate, UI contract (28), UI preview
  (2), optimization test, CSS equivalence comparison and `git diff --check`
  passed. The first removal commit `5a68e6be41136cdabff7d20b84c1d8c750b59c49`
  was pushed and its exact OpenKill Development CI succeeded:
  https://github.com/dinggood615/openkill/actions/runs/36294816940.
- Delivery: the second cleanup commit
  `b7768be37ed8ad5cd05ae6b4aa26fd3f8cc17a5b` was pushed after the same local
  gates. Its exact OpenKill Development CI succeeded:
  https://github.com/dinggood615/openkill/actions/runs/36294955817.

## Follow-up audit: retired translations and compatibility surfaces (2026-09-27)

- Audit targets are the remaining OixCloud translation entries, the
  announcement compatibility endpoint and other explicit no-op/fallback
  contracts, plus CSS selectors not referenced by current templates or
  scripts.
- Keep the announcement endpoint as an empty compatibility response for cached
  frontends unless its callers and upgrade behavior are removed together.
  Keep network/parser no-op and fallback functions that protect continuity or
  BusyBox compatibility. A translation entry is removable only when its
  message ID has no live source reference and is not needed by a retained
  compatibility page.
- For CSS, compare selectors against all LuCI templates, inline hooks,
  generated preview markup and runtime JavaScript before removing them. Record
  the selector evidence and rerun UI contract/preview and package-path gates.
- OixCloud translation audit result: 16 message blocks in each retained
  Chinese and Spanish catalog had no live source reference. They were removed;
  `check-openkill-i18n.sh`, optimization/UI tests, local gate and diff checks
  passed. The announcement endpoint remains a deliberate empty compatibility
  response, and network/fallback no-op contracts remain in use.
- The translation cleanup commit
  `3abdfef6cf6bf6c8afdfb38d7d0f17649c202e73` was pushed and its exact
  Development CI succeeded:
  https://github.com/dinggood615/openkill/actions/runs/36295347743.

## CSS ownership refactor: baseline and runtime-status phase (2026-09-27)

- Scope: this staged change is limited to OpenKill-scoped CSS variables, rule
  ownership, load order, responsive layout and accessibility presentation.
  It must preserve CBI field identities, UCI values, controller endpoints,
  DOM event bindings, validation and save/apply semantics.  It must not change
  DNS, proxy, node or network behavior.
- Baseline source: `master` at
  `40773210d49770dbc55faec15fddeecd14b2cce0`, with a clean worktree before this
  phase. `oc.css` is 9,482 lines / 305,557 bytes and `flat.css` is 1,588 lines /
  59,202 bytes.  `status.htm` and `settings_theme.htm` load `oc.css` then
  `flat.css`; the package Makefile currently prunes only staged `oc.css`.
- Inventory: `oc.css` declares 488 custom-property assignments and 260
  `!important` uses, including legacy `--row-1-height` through
  `--row-4-height`, fixed dashboard tracks and row minimums.  `flat.css`
  declares 26 custom-property assignments and one `!important`, but contains
  multiple later dashboard overrides, including a terminal fixed-row repair.
  The first phase moves the content-sized runtime contract to its primary
  status rules and removes the retired row tokens and duplicate repair layer;
  it does not change status markup or scripts.
- Style contract: LuCI theme values are read first, OpenKill variables are
  scoped to `.oc` / `#cbi-openkill`, common components follow, then page layout
  and responsive rules.  Old variables remain only while referenced.  New
  selectors must not style LuCI system pages or other applications.
- Verification plan: rebuild the preview from the real templates and final
  CSS, capture an available-browser desktop baseline, and record its limits.
  Run UI contracts, preview and interaction checks, CSS/package checks,
  `sh scripts/local-gate.sh`, and `git diff --check` for every phase.  Exact
  viewport/zoom and light-theme checks require browser controls not currently
  exposed by the local preview environment and remain explicitly unverified if
  unavailable.  Device access, CENTRAL_ACTIVE, central nft, WAN/default route
  and packet-path tests remain forbidden.
- Runtime-status phase: removed the four legacy row-height tokens, fixed grid
  tracks, nth-row minimums and the duplicated late repair block.  The primary
  component/layout rules now use content-sized grid rows.  Local UI contract,
  preview and interaction tests, final CSS/package validation, `git diff
  --check` and the local gate passed.  The real local preview at 1536 x 730
  CSS px (DPR 1.25, dark theme) retained equal 724 px cards, a 1461 px grid,
  no horizontal overflow, `grid-template-rows: none`, and the same computed
  card surface before and after.  Source commit
  `bd4242aa4d5547d811ada439fbd2f8299a93ba62` is pushed; Development CI #281
  passed: https://github.com/dinggood615/openkill/actions/runs/36292472825 .
- Next action: consolidate plugin-settings card layout ownership.  Retain the
  existing DOM reparenting, field order and CBI rows while merging duplicate
  card-stack/card layout declarations into the documented layout layer and
  removing containment that can defer an expanded card's content.

## CSS ownership refactor: settings-card phase evidence (2026-09-27)

- Completed: `flat.css` now has one canonical settings-card layout section.
  It owns the two-column grid, content-sized rows, card flex flow and desktop
  stretch behavior.  Earlier duplicate stack/card declarations and the late
  precedence copy were removed.  The change does not alter `settings_theme.htm`
  or any CBI field, tab, event, validation or save/apply code.
- Source evidence: `61bebfdb7700ebe16723b6297f3e73a1445bc2b3`
  (`ui: consolidate settings card layout rules`) is pushed to `master`.
  `test-ui-contract.py` (28 tests), preview and interaction tests,
  `git diff --check`, CSS/package validation and `sh scripts/local-gate.sh`
  passed. Development CI #282 passed for that exact source:
  https://github.com/dinggood615/openkill/actions/runs/36292702542 .
- Baseline delta after the two phases: `oc.css` is 9,455 lines / 304,427 bytes
  and `flat.css` is 1,546 lines / 57,639 bytes, down 27 lines / 1,130 bytes
  and 42 lines / 1,563 bytes respectively. `!important` counts remain 260 in
  `oc.css` and one in `flat.css`; those remaining uses require page-by-page
  ownership review rather than broad removal.
- Browser evidence: the local preview is built from the real status template
  and final CSS.  In available Chrome it rendered the runtime dashboard at
  1536 x 730 CSS px, DPR 1.25, dark-theme mode, with two 724 px cards in a
  1461 px grid and no horizontal overflow before and after the status change.
  The preview generator does not render a router-backed CBI settings map, and
  Playwright is unavailable; settings-card browser screenshots, exact target
  viewport/zoom runs, light theme and router integration remain unverified.
- Next action: use the same measured, single-page approach for configuration
  management, then subscription, overwrite, node/policy, logs, diagnostics,
  component management and dialogs.  Each page requires its own baseline,
  bounded commit and exact-commit Development CI.  No RC build, version bump
  or formal release is authorized for this partial CSS refactor.

## LuCI theme-aligned UI refresh (2026-09-27)

- Scope: visual and layout work only. The change may adjust page structure,
  theme-aware CSS variables, responsive layout, focus states and accessibility
  text, but must preserve every CBI field name, UCI value, request endpoint,
  event binding, validation rule and save/apply behavior.
- UI contract: OpenKill pages inherit the active LuCI theme's page shell and
  typography where available. OpenKill-only fallback tokens are scoped below
  `.oc` or `#cbi-openkill.openkill-settings`; no selector may style LuCI system
  pages or other plugins.
- Verification scope: inspect the real template DOM and final packaged CSS,
  then validate locally and in an available browser at desktop, tablet and
  phone viewports. Device access, `CENTRAL_ACTIVE`, central nft state, WAN,
  default-gateway and packet-path tests remain outside this iteration.
- Current implementation finding: `oc.css` contains legacy and current token
  sets with late page-specific overrides, while `flat.css` is loaded after it
  and changes shared widths and surfaces. Settings cards are created by
  `settings_theme.htm`, whereas the status dashboard has a separate custom DOM;
  the refresh must preserve both structures and their runtime hooks.
- Implemented: added an OpenKill-only LuCI theme bridge in `oc.css`, with
  page-body capture of theme variables so legacy `.oc` tokens cannot shadow
  the active LuCI theme.  `flat.css` now has one terminal layout precedence
  layer for natural-height cards, wrapping controls, scoped surfaces and
  responsive grids; the earlier duplicate bridge was removed.
- Local evidence: `test-ui-contract.py` (27 passed), `test-ui-preview.py` (2
  passed), `test-ui-interactions.py` (1 passed),
  `test-autonomous-workflow.py -v` (10 passed), `git diff --check` and
  `sh scripts/local-gate.sh` passed.  The preview was rebuilt from the real
  templates and served locally with the LuCI asset path; Chrome rendered the
  themed desktop dashboard without console-visible errors.
- Browser boundary: the repository browser test reports
  `PLAYWRIGHT_UNAVAILABLE`; the connected Chrome preview has no viewport
  override API in this environment, so exact 1920/1366/1200/768/390 CSS-pixel
  and 125% measurements, light-theme rendering, and device/LuCI integration
  remain unverified.  No device or packet-path test was run.
- Exact source commit: `115dda30ca6e69335cc405cf9644609d2503431f`
  (`ui: align OpenKill pages with LuCI theme`) is pushed to `master`.
- Development CI: OpenKill Development CI #279 passed for that exact commit:
  https://github.com/dinggood615/openkill/actions/runs/36291313754 .  The
  accompanying cache cleanup run #344 also passed.
- No version bump, RC build or Formal Release was run in this UI review; the
  current formal release remains 2026-1168.  A later release must rerun the
  full RC and release gates from the then-current source commit.

## Release build acceleration and version 2026-1168 (2026-09-27)

- Scope: optimize only the RC/Formal Release build and publication path. The
  package source and runtime/network behavior are unchanged. Both workflows
  will reuse a content-keyed OpenWrt SDK cache, skip redundant SDK download and
  extraction when the cached tree is valid, and invoke the OpenKill package
  makefile directly so unrelated SDK packages are never compiled.
- Release contract: retain the explicit `release_gate=true` and
  `publish=true` Formal Release gate, exact-source checkout, version/release
  note checks, package audit, SHA256 and channel publication. Cache hits may
  shorten preparation but may not bypass source validation, package selection
  checks or artifact audit. The source version will advance once to
  `2026-1168` only after the optimized path passes local gates and exact-commit
  Development CI.
- Verification boundary: local workflow-contract and shell checks are required.
  GitHub RC/Formal workflows and package publication are remote gates; no
  router/device access, `CENTRAL_ACTIVE`, central nft state, WAN/default
  gateway changes or packet-path tests are authorized in this iteration.
- Implementation evidence on the resulting source `753e465e618b2de58055b0c17c79469d401d3f98`:
  RC and Formal workflows use content-keyed SDK caches, reuse validated SDK
  trees and feed/host preparation markers, cache CodeMirror dependencies, and
  invoke the OpenKill package makefile directly. Version checks,
  package-selection guards, artifact audits and the explicit release gates
  remain in place. APK remains an optional target and was disabled for this
  IPK-only release.
- Local verification: `python scripts/test-autonomous-workflow.py -v`,
  `sh scripts/local-gate.sh` (via WSL), and `git diff --check` passed. The
  first exact commit `091ef87809120436c69748e59607616e86317147` reached the
  Development CI but its runtime matrix exposed a pre-existing uncommitted
  settings-test assertion that still expected six tabs. The bounded repair is
  commit `d0e88b229c8baccb8a556cadc8086808536382ef`, which records the already
  present seven-tab layout contract. Development CI Run 274 for that exact
  commit passed; the earlier failure was not a workflow/build regression.
- Exact source Development CI Run 277 passed for the resulting commit.
- RC Build Run 100 passed from that exact source. Its audited candidate
  `luci-app-openkill_2026-1168_all.ipk` has SHA256
  `f58f1be0de7bf9932d596258c397adf761d8c083e20b19719d5b26235d3deb45`.
  Package metadata, conffile preservation, maintainer-script deletion,
  stale-reference and runtime-sensitive-content audits passed.
- Formal Release Run 193 passed with `release_gate=true` and `publish=true`.
  It published [v2026-1168-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1168-ipk)
  from the exact source commit. The downloaded formal IPK matches the
  published asset and has SHA256
  `c11a927188583bab82766da57a7cbfc651f507d284687396ebeb3a2db39f4fb6`.
  The package contains version `2026-1168`, `/etc/config/openkill` as a
  conffile, and executable init/service scripts with no private test-node
  material. The previous v2026-1167 release remains available for rollback.
- The two earlier formal attempts (Runs 191 and 192) failed before publication
  due to SDK path and cached feed/host preparation gaps; both were repaired
  before Run 193. No device, router, VPS or packet-path validation was run.

## NaiveProxy service tab and stable component update (2026-09-27)

- Scope: move the independent NaiveProxy service into the `插件设置` tab
  sequence between `网络与分流` and `兼容与辅助`; remove its duplicate
  compatibility-card layout entry while preserving the existing independent
  service template and credential boundary.
- Update contract: add a permission-checked service operation that resolves
  only the official stable release metadata, verifies URL/size/SHA256/ELF and
  loader before atomic replacement, retains the previous component on failure,
  and never changes OpenKill UCI, user YAML, Mihomo or strategy groups.
- Verification boundary: local source, shell, UI-contract and local-gate
  checks are required. The current plan still does not authorize device writes,
  package installation, remote VPS authentication or packet-path tests; those
  remain pending unless a later plan explicitly authorizes a device phase.
- Next action: run focused NaiveProxy/settings tests and the full local gate,
  review the diff, then commit the bounded change. Browser rendering remains
  subject to local browser-tool availability.

### Implementation evidence

- Source commit `293632aaeabd43f1d1f4f02d086a0819d23d3dae` moves the service
  DummyValue into a dedicated `naive_service` Plugin Settings tab between
  Network & Routing and Compatibility, updates legacy redirects, and removes
  the duplicate compatibility layout entry.
- The card now exposes an official-stable-component update operation. The
  bridge resolves official metadata, requires a complete URL/SHA256/size set,
  and delegates to the existing verified atomic installer; failures retain
  the previous component and node data.
- Local UI contract, import behavior, optimization, integration, shell syntax,
  `sh scripts/local-gate.sh`, and `git diff --check` passed. The standalone
  health test was not completed because the Windows host cannot provide its
  network timing fixture; browser rendering and device/VPS validation remain
  unverified. Development CI for the exact commit is pending inspection.
- Follow-up local verification passed the updated standalone integration
  contract (including the stable-component update operation), UI contract,
  link-import behavior and `git diff --check`. No version increment or release
  was performed because the required device/VPS phase is still outside the
  authorized boundary.
- Resume condition: a future plan must explicitly authorize the test-device
  phase and provide its permitted read/write scope before package installation,
  component update, node start or VPS authentication can be attempted. Until
  then the implementation remains on `master` at the observed HEAD and the
  release gate stays intentionally pending.

## Standalone NaiveProxy card placement and legacy-config removal (2026-09-26)

### Follow-up: import diagnostics and compatibility card placement

- Scope: repair independent NaiveProxy share-link decoding and component
  diagnostics, and move the existing ZeroTier fields into the compatibility
  page's `远程访问绕过` card. The system-maintenance fields remain owned by
  the maintenance tab and occupy the former ZeroTier card position beside
  Mihomo capabilities. UCI names, defaults, validation and service behavior
  are unchanged.
- Import contract: percent-encoded userinfo and fragments are decoded only by
  the independent service after the browser's redacted preview; credentials
  remain outside OpenKill state, logs and responses.
- Component contract: the standalone manifest now records whether the binary
  is missing, non-executable or failed its loader/version probe. The page no
  longer describes an unavailable component as merely having a registered
  path.
- Verification boundary: local fixture, shell syntax, UI contracts and local
  gate are required. Device and real VPS status remain unverified and no
  device-side cleanup or packet-path test is authorized.

- Scope: place the `NaiveProxy 独立服务` card in the compatibility tab's
  two-column grid to the right of `OpenVPN 精确兼容`, with equal-width rows
  and a single-column mobile fallback. Keep CBI fields and service actions in
  one card; do not alter network policy fields or runtime semantics.
- Legacy contract: remove the old OpenKill Naive migration warning and old
  UCI/server-section read path from the visible service status. Add an
  explicit, permission-checked and idempotent cleanup operation that backs up
  only legacy Naive UCI values and `type: naiveproxy` sections before removal;
  it never copies credentials to the standalone service, modifies user YAML,
  or deletes unrelated nodes. The operation is covered by local fixtures but
  is not executed on a device during this local-only iteration.
- Import contract: make the standalone card's import action open a dedicated
  link-first form. A supported `naive+https://`/`naiveproxy://` link is parsed
  structurally, previewed with redacted credentials, and maps supported
  fields before the user saves to the independent service. Unknown parameters
  remain visible as warnings and no credential is returned to OpenKill.
- Install contract: keep the one-click standalone stage ahead of any service
  start; resolve architecture/libc/loader/dependency metadata from the
  official asset resolver and never use legacy OpenKill fields as defaults.
- Verification boundary: local UI contracts, cleanup/install/import-parser
  behavior, shell syntax and local-gate are required. Browser rendering is
  required against a local preview when available; device state and real VPS
  authentication remain unverified under the current plan.
- Local implementation evidence: the compatibility card builder now moves the
  standalone DummyValue before it creates the two-column grid; the retired
  status scanner no longer reads legacy UCI values. The explicit cleanup
  command creates a mode-600 local backup before deleting only named legacy
  options and `servers` sections of type `naiveproxy`. The one-click script
  and package post-install invoke that idempotent cleanup without using it as
  an independent-service input. The import dialog is link-first and the
  standalone service reparses the submitted link before persisting it.
- Local verification: standalone fixture, import behavior, integration and UI
  contract tests passed; `scripts/local-gate.sh` and `git diff --check`
  passed. The browser suite reported `PLAYWRIGHT_UNAVAILABLE`; device and VPS
  checks remain unverified and are not authorized by this plan.
- Delivery evidence: implementation commit `ca60159c4808f8f28aa8b07b4332ac6c3c4b9474`
  passed [Development CI](https://github.com/dinggood615/openkill/actions/runs/36248595925).
  Versioned source `37421e6f34afa4a9827c81826f5338ea1a349933` passed exact
  [Development CI](https://github.com/dinggood615/openkill/actions/runs/36248749481).
  The [RC Build](https://github.com/dinggood615/openkill/actions/runs/36248842311)
  passed from that source; its IPK SHA256 was
  `8df405a491a1285645a215cd8b258a23510be7222bfabdb5dc7b77b69d86454d`.
  The [Formal Release](https://github.com/dinggood615/openkill/actions/runs/36249211506)
  passed with both required gates and published
  [v2026-1163-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1163-ipk).
  The downloaded formal IPK SHA256 is
  `6b80d107eb0182b669574e86e76541c3f426334fc23a49a1d6a9861f66e11b58`.

## NaiveProxy legacy cleanup and one-click standalone component (2026-09-26)

- Scope: remove the retired `NaiveProxy 辅助组件` presentation and old
  OpenKill-owned node/health writers; keep only the independent
  `naiveproxy-bridge` card and its redacted read-only adapter. Existing
  `naive_*` UCI and server sections are migration evidence and will not be
  deleted or rewritten by this change.
- Installation contract: the one-click installer must install the OpenKill
  package, then resolve and verify an official NaiveProxy OpenWrt asset and
  place the executable under `/etc/naiveproxy/naive`. Version, asset, URL,
  size and expected SHA256 stay bound; failure keeps the previous executable
  and reports the independent component stage.
- Ownership contract: node JSON, loopback ports, procd lifecycle and health
  results remain under `/etc/naiveproxy` and `/var/run/naiveproxy`. OpenKill
  does not save credentials, inject Mihomo nodes, or rewrite user YAML.
- Compatibility contract: old routes remain read-only redirects/status
  aliases; old helper scripts and UCI display options are removed only after
  all production references and tests are migrated. Manual SOCKS5 YAML
  remains user-owned and is never deleted during upgrade or rollback.
- Verification boundary: local fixtures, shell syntax, UI contracts and
  installer contracts are required. Device, browser rendering and real VPS
  authentication remain unverified unless a later plan explicitly authorizes
  them.
- Local evidence before commit: the independent bridge fixture covers health,
  redacted YAML and offline install replacement/rollback; integration,
  installer, runtime, UI-contract, POSIX syntax and `sh scripts/local-gate.sh`
  all pass. Browser rendering, device state and VPS authentication remain
  pending by design.

## 2026-1162 release preparation (2026-09-26)

- Implementation baseline: `af6ac6eef83b74b1e5a36d3bac3165da9ddd9652` on
  `master`; exact OpenKill Development CI run `36243366039` passed.
- Versioned source commit: `adb6fea9c11731693fa9da905d977704d31267d8`;
  exact Development CI run `36243523330` passed. This is the only source
  version increment for this delivery.
- RC Build run `36243671292` passed from the exact versioned source. The
  candidate IPK is 7,689,820 bytes with SHA256
  `3d9c58a67a59f1cd586fb826bf889a34713c565caa18ebdaa6c2ad1b83a4698d`;
  package metadata, conffile preservation, stale-reference and sensitive
  content audits passed. The package contains the standalone component
  installer/service and no retired `openkill_naive*` files.
- Formal Release run `36244585080` passed with `release_gate=true` and
  `publish=true`. It published
  [v2026-1162-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1162-ipk)
  from the exact versioned source. The formal IPK is 9,233,381 bytes with
  independently verified SHA256
  `e0f9ee456326b555da828c6c9bbf0a69a2e0cc8956adce6852d1f315a8ab1256`.
- Rollback remains `v2026-1161-ipk`; preserve `/etc/naiveproxy` and the
  user-managed YAML, stop the standalone bridge if needed, reinstall the
  previous IPK, and leave legacy configuration available for migration.
- Local fixtures, installer/standalone/integration/runtime/UI contracts,
  POSIX syntax, `sh scripts/local-gate.sh`, `git diff --check`, RC and Formal
  audits passed. Browser rendering, device state and real VPS authentication
  were not run under the current local-only plan and remain unverified.

## 2026-1161 release preparation (2026-09-26)

- Source implementation is on master commit `8adb826` and its exact
  Development CI run passed (`36239900863`). The next release increments the
  package and installer metadata to `2026-1161`.
- The release scope is limited to the VPN policy layout and independent
  NaiveProxy control card already recorded below. No device or VPS test is
  authorized in this iteration; browser rendering is also pending.
- Next action: run local gates on the versioned source, push the release
  preparation commit, verify its exact Development CI, then run the RC Build
  and Formal Release gates. Record their links and package hashes here.
- Release evidence: versioned source commit `26f16a3` passed exact
  Development CI run `36240077008`; RC Build run `36240284537` passed with
  candidate digest
  `ed119de959a90be3ce3680d8352be10058451eb4960c13fadc2c8aee417d9212`.
  Formal Release run `36240505507` passed with tag `v2026-1161-ipk` and
  published IPK digest
  `259fddb16614bd210ca61ccc2a4b3e0041bf321a5c89c85b8a0e1aa053cbdcdd`.
  Release URL: https://github.com/dinggood615/openkill/releases/tag/v2026-1161-ipk
- Device installation, browser rendering and real VPS/packet-path tests remain
  unverified under this plan.

## NaiveProxy controls and VPN policy layout (2026-09-26)

- Scope: move the existing device and bypass-router compatibility fields into
  the `VPN 访问策略` card while preserving their UCI names, defaults, depends
  rules and network semantics. Keep the independent NaiveProxy bridge as a
  separate equal-width card in the compatibility page.
- Service contract: add only a permission-checked local control boundary for
  `naiveproxy-bridge`. Start, stop, node import and health actions remain owned
  by the standalone service; OpenKill must not write Naive credentials to UCI,
  pass secrets in command arguments, modify the selected YAML, or restart
  Mihomo. Responses contain redacted identifiers and state only.
- UI contract: the card exposes service state, add/import actions, per-node
  test latency, refresh and diagnostics. Existing read-only status and manual
  SOCKS5 YAML ownership remain authoritative. Device and VPS tests are outside
  this iteration unless a later plan explicitly authorizes them.
- Failure contract: invalid sessions, malformed requests, duplicate tasks,
  missing component, port conflicts and probe failures must return a specific
  redacted stage. Remote failures never trigger unrelated restarts or DIRECT.

## NaiveProxy standalone bridge and manual YAML ownership (2026-09-26)

- Scope: split NaiveProxy component/node ownership from OpenKill. The new
  standalone bridge owns `/etc/naiveproxy`, procd instances, loopback SOCKS5
  listeners and per-node HTTPS health results. OpenKill becomes a read-only
  status view and a credential-free YAML snippet generator; it must not write
  Naive credentials, auto-start helpers, inject proxy entries or rewrite the
  user's YAML.
- Config contract: standalone node JSON is mode 600 under `/etc/naiveproxy`;
  runtime state is sanitized and bounded under `/var/run/naiveproxy`. The
  OpenKill UCI and selected YAML remain user-owned. Legacy OpenKill Naive data
  is migration evidence only and is never silently deleted or copied.
- Lifecycle contract: one stable node ID maps to one loopback port and one
  procd instance. Manual start/stop is authoritative; local process/listener
  failures may trigger bounded per-instance recovery, while remote probe
  failures never restart unrelated services or fall back to DIRECT.
- Health contract: probes use the matching SOCKS5 listener and a fixed HTTPS
  allowlist with bounded timeout/size/redirects. Displayed delay is HTTPS
  request elapsed time, not ping, UDP or full Mihomo routing verification.
- Verification boundary: local fixtures must prove independent lifecycle,
  credential redaction, YAML non-rewrite and status expiry. Device and remote
  VPS tests remain forbidden unless a later CURRENT section explicitly
  authorizes them.
- Implementation evidence (working tree): added the independent
  `naiveproxy-bridge` procd service and `naiveproxy-standalone.sh` library;
  node JSON and runtime state stay under `/etc/naiveproxy` and
  `/var/run/naiveproxy`, while OpenKill reads only the redacted manifest and
  generated credential-free SOCKS5 snippets. Legacy OpenKill Naive routes now
  redirect or expose read-only status, and the OpenKill init script no longer
  starts, stops, probes or injects Naive nodes.
- Local checks completed: standalone fixture (component probe, protected
  config, loopback probe, HTTPS timing, expiry fields and YAML redaction),
  standalone integration contract, UI contract/interactions, optimization
  checks, POSIX syntax and `sh scripts/local-gate.sh`. Device, browser and
  remote VPS behavior remain unverified by plan.

## OpenKill startup preflight and NaiveProxy compatibility repair (2026-09-26)

- Scope: diagnose the reported startup abort before Mihomo launch, make the
  generated controller listener deterministic and valid, preserve strict DNS
  privacy fail-closed behavior with an actionable selectable-group diagnostic,
  and verify the NaiveProxy helper's VPS-facing configuration without changing
  the NaiveProxy protocol or the user's YAML ownership.
- Startup contract: `dashboard_bind_address` and `cn_port` are normalized by
  the same address/port helpers used by runtime API probes before YAML
  generation. Invalid legacy values fall back to loopback/9090 and are
  recorded as a repair reason; a generated invalid `external-controller`
  never replaces the last-good profile. Strict DNS still refuses a profile
  with no selectable proxy group, but reports the missing group and preserves
  the active configuration.
- NaiveProxy contract: one protected JSON configuration and one loopback
  SOCKS5 listener per enabled stable node; only supported `https`/`quic`
  transports are emitted, credentials stay out of logs and YAML snippets, and
  a helper/remote failure never becomes `DIRECT`. The component path and ELF
  probe remain authoritative; no device-specific binary or node data is added
  to the repository.
- Device phase: the latest user request explicitly authorizes **read-only**
  diagnostics on the test host `192.168.1.103` via the existing SSH alias.
  The phase is limited to version/path/UCI/log/process/listener inspection and
  redacted generated-config checks. It must not write UCI, restart services,
  install packages, enable `CENTRAL_ACTIVE`, apply central nft state, or run
  packet-path tests. If the host is unreachable, local evidence remains the
  source of truth and the gap is recorded.
- Verification: add regression fixtures for malformed controller values,
  strict-DNS missing groups, Naive URL/config generation and credential
  redaction; run the local gate and exact-commit Development CI before RC and
  Formal Release.

### Current evidence (before implementation commit)

- Source baseline observed at `474c50e1fef0f3888e504cb2e4fc214fd902ce08`; the
  worktree retains only this startup/Naive repair plus this plan update.
- Read-only test-host inspection is authorized for this iteration. The host
  reports `luci-app-openkill 2026-1158`, an executable x86_64 NaiveProxy
  `150.0.7871.63` at `/etc/openkill/core/naive`, and no running OpenKill or
  Naive instance. Its selected YAML contains an empty `proxy-groups:` and its
  UCI has no `groups` sections while `dns_privacy_mode` is `strict`; this is the
  direct cause of the startup transaction abort. The same logs contain helper
  `SIGTRAP` exits, which remain a separate runtime/remote compatibility fault;
  no packet-path or remote probe was run.
- Local changes now normalize the controller bind/port before generation,
  return a non-zero status for a failed YAML transaction, preserve the active
  profile, and record a specific startup failure reason. Strict DNS accepts
  only a real selectable proxy, provider, or include-all group and reports the
  required repair. Naive status requires a local version probe, rejects empty
  credentials, maps legacy `tls` to HTTPS, and reports a stopped helper as a
  local lifecycle failure.
- Local evidence so far: `scripts/test-runtime.py` (31 tests, 3 environment
  skips), `scripts/test-naiveproxy-integration.py`,
  `scripts/test-naiveproxy-health.py`, `scripts/test-openkill-optimization.py`,
  POSIX syntax checks, `git diff --check`, and `sh scripts/local-gate.sh` all
  pass. The Windows host emits harmless WSL/GBK reader warnings for the
  optimization fixture; the process exits successfully. Device reinstallation
  and remote VPS connectivity remain pending and are not claimed here.

### 2026-1159 delivery evidence

- Implementation commit `c22e3d36efcc799dd7e3c1b0c6fb251d3013838d` contains the
  startup transaction, listener validation, strict-DNS diagnostics and
  NaiveProxy component/lifecycle fixes. Version metadata and release notes were
  prepared in `6b20f976fe67f66f165a7ac22e5fe27e8d1a2e45`; both commits are on
  `master` and the version commit is the published source.
- The exact version commit's Development CI passed: [run
  36233800250](https://github.com/dinggood615/openkill/actions/runs/36233800250).
  The source gate and local gate passed for `2026-1159`; `git diff --check` was
  clean.
- RC Build from the exact version commit passed: [run
  36233919434](https://github.com/dinggood615/openkill/actions/runs/36233919434).
  The candidate IPK is `luci-app-openkill_2026-1159_all.ipk`, 7,706,023 bytes,
  SHA-256
  `6965957aacc645a8880877f2840daf2e1db14bc964c3593f94d773fec17dd0ef`.
  Its audit artifact digest is
  `sha256:7fbba5bd71d73321f1a25347e1c4af69f240f3211e0ca162d68f011b79088771`;
  metadata, conffile preservation, maintainer-script deletion, stale-reference
  and sensitive-content checks passed under `D:\\openkill-cache\\rc-2026-1159`.
- Formal Release passed with `release_gate=true` and `publish=true`: [run
  36234170503](https://github.com/dinggood615/openkill/actions/runs/36234170503).
  Published [v2026-1159-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1159-ipk)
  from source `6b20f976fe67f66f165a7ac22e5fe27e8d1a2e45`. The public release
  asset `luci-app-openkill_2026-1159_all.ipk` is 9,246,266 bytes with SHA-256
  `2758a19fbec1b581a5f7c4d0e42c2804ad4a87ca97d542e0a3b2f895b552a2d3`.
  The formal workflow artifact digest is
  `sha256:5b02a8e48199ce06765a6992dc422bf45c52a9292f087e6e92d7eefe02ec5e85`;
  the package control record is version `2026-1159`, architecture `all`, and
  preserves `/etc/config/openkill`. The downloaded release audit is retained
  under `D:\\openkill-cache\\formal-2026-1159`.
- The authorized device phase was read-only. It confirmed OpenKill `2026-1158`,
  an executable `/etc/openkill/core/naive` reporting `150.0.7871.63`, strict
  DNS with no selectable proxy group, no running helper, and historical
  NaiveProxy `SIGTRAP` exits. No UCI/config write, restart, package install,
  packet-path test, central nft change or remote VPS authentication was done.
  The strict-DNS failure must be repaired by adding a real selectable proxy
  group (including the generated SOCKS5 name) or intentionally changing the
  privacy mode; it must not silently fall back to `DIRECT`. The SIGTRAP remains
  a separate device/runtime compatibility issue and is not claimed fixed by this
  release.
- Rollback is the retained `v2026-1158-ipk` package/tag after backing up the
  device configuration and preserving the user's existing nodes and YAML. No
  credentials, private node values or complete share links are recorded here.

## NaiveProxy manual health diagnosis and compact compatibility card (2026-09-26)

- Scope: clarify the screenshot state where `final-yaml-missing-node` appears
  while the helper is in manual YAML mode, and reduce the NaiveProxy card's
  default UI without changing node credentials, DNS, routing, firewall, YAML
  ownership or the helper protocol. The final-YAML result remains read-only
  context; it must never turn a successful loopback probe into a failure.
- Health contract: the primary status is the bounded probe through that node's
  `127.0.0.1` SOCKS5 listener. Mihomo/YAML membership is shown as a separate
  diagnostic and remains expected to be missing until the user copies the
  credential-free snippet into the selected YAML and adds its name to a
  strategy group. No direct fallback is allowed.
- UI contract: keep component status, version/architecture, install, node
  management, loopback YAML and per-node testing available; move URL, digest,
  asset metadata, removal and detailed Mihomo diagnostics behind accessible
  details. Remove duplicate default controls and the redundant Mihomo table
  column while preserving the full row diagnostic.
- Boundary: the current plan and AGENTS.md forbid device and packet-path
  access in this iteration. Local fixtures will reproduce a missing-final-YAML
  case and prove it does not suppress loopback health; device/remote causes
  remain pending a separately authorized plan.

### 2026-1158 delivery evidence

- Diagnosis: in manual YAML mode, `final-yaml-missing-node` is an independent
  Mihomo/YAML membership diagnostic. It means the credential-free loopback
  snippet has not been copied into the selected YAML and strategy group. The
  screenshot's `探测失败` remains the separate bounded loopback HTTPS probe
  result; the exact helper, credential or remote cause requires a device phase
  and is not inferred from the YAML diagnostic.
- Fix commit `929e27301ae8bc181396292e890d3d825947d46f` keeps the loopback
  probe authoritative, preserves the separate Mihomo detail, moves component
  metadata and maintenance actions behind accessible details, shortens the
  default controls, removes the duplicate Mihomo table column and adds a
  no-horizontal-scroll mobile card layout. Its exact Development CI passed as
  run `36230543078`:
  https://github.com/dinggood615/openkill/actions/runs/36230543078
- Version commit `f1109692182c91f93b5181bb2286f5bfc8c7fdcb` advances the source
  metadata and release notes to `2026-1158`. Its exact Development CI passed as
  run `36230738478`:
  https://github.com/dinggood615/openkill/actions/runs/36230738478
- RC Build run `36230857780` passed from `f110969` and produced
  `luci-app-openkill_2026-1158_all.ipk` (7,703,994 bytes), SHA256
  `c0fd65f5fb4f755b9f6f7f0378c7ae80f76de33c37abcc875d55676e4482fbc7`.
  The artifact digest is
  `sha256:26b5631318ea8f737e0ee02ceff0dae2839a91b401e76f84829c0536c8781b81`;
  the downloaded audit is retained under
  `D:\\openkill-cache\\rc-2026-1158`.
- Formal Release run `36231157068` passed with `release_gate=true` and
  `publish=true` from `f110969`:
  https://github.com/dinggood615/openkill/actions/runs/36231157068
  Published release:
  https://github.com/dinggood615/openkill/releases/tag/v2026-1158-ipk
  contains `luci-app-openkill_2026-1158_all.ipk` (9,245,110 bytes), SHA256
  `dc68ef2a978f6f5227396073e215a5274b094436150c64cc913fb8f88ed31753`.
  The formal artifact digest is
  `sha256:71f02df3fdc35edbe927f86423cc7f6c5d3427c45626d9afd9ab213b82dc922d`;
  the downloaded package and extracted audit are retained under
  `D:\\openkill-cache\\formal-2026-1158`.
- Package audit confirmed version `2026-1158`, architecture `all`, the
  `/etc/config/openkill` conffile, root-owned executable helper scripts, the
  final `oc.css` and health script, and no private-node markers. Local health,
  integration/UI contract, interaction/preview, POSIX syntax, local-gate and
  diff checks passed. The browser preview was inspected; Playwright is not
  available on this workstation, so a complete automated viewport matrix is
  not claimed.
- Device, packet-path and real Naive endpoint tests remain pending because
  AGENTS.md and this iteration's plan forbid device access. No CENTRAL_ACTIVE,
  central nft, WAN, gateway, DNS, IPv6 or TUN change was made. Rollback is the
  retained `v2026-1157-ipk` package plus the user's existing configuration and
  manual YAML backups.

## NaiveProxy manual YAML mode and shared OpenKill theme (2026-09-26)

- Scope: move the NaiveProxy contract to manual YAML ownership, keep the
  helper responsible only for protected per-node configuration and loopback
  SOCKS5 listeners, add per-node health evidence and bounded local recovery,
  and unify the OpenKill page surfaces and theme tokens. This supersedes the
  previous automatic bridge *injection* contract for new applications while
  retaining the legacy UCI value for migration visibility.
- Contract: the UI no longer offers automatic Mihomo injection. An enabled
  NaiveProxy node is prepared and supervised independently; the generated
  credential-free SOCKS5 snippet is the only Mihomo hand-off. Existing YAML
  and user strategy groups are preserved. If a legacy `auto` value is found,
  the page reports that manual migration is required and does not rewrite the
  user's YAML or silently fall back to DIRECT.
- Lifecycle: each stable node ID owns one 127.0.0.1 TCP SOCKS5 port, a mode-
  600 helper JSON file and one procd instance. Port ownership, PID and
  configuration generation are checked before reporting local readiness.
  Recovery is limited to the affected instance with cooling and bounded
  retries; a remote probe failure never restarts the whole proxy or changes a
  policy selection.
- Health: probes use the matching loopback SOCKS5 path with a fixed HTTPS
  target/strict redirect and size limits. Results are per node, expire after
  bounded time, and expose auxiliary-chain evidence separately from any
  read-only Mihomo/YAML diagnostic. Credentials and response bodies are not
  persisted.
- UI: OpenKill pages share scoped light/dark surface variables, card borders,
  controls and spacing. No DNS, IPv6, TUN, firewall, legacy-writer parser or
  ABI semantics are changed. Temporary artifacts remain under
  `D:\openkill-cache` and no device or packet-path test is part of this local
  iteration.
- Verification gate: update the manual-mode fixtures, health and UI contract
  tests, run POSIX checks, `scripts/local-gate.sh` and `git diff --check`,
  then verify the exact Development CI commit before RC/Formal Release.

## NaiveProxy automatic bridge diagnostics (2026-09-26)

- Scope: repair the automatic Mihomo bridge path without changing NaiveProxy,
  DNS, routing, firewall, legacy parser or ABI semantics. The change covers
  generator failure reporting, bridge-node presence checks and strategy-group
  diagnostics. Credentials and private node data remain outside logs, tests,
  reports and package artifacts.
- Contract: an enabled NaiveProxy node in automatic mode must either produce a
  credential-free `type: socks5` entry and an explicit strategy-group
  reference, or record a redacted, stage-specific reason. It must never be
  silently omitted or replaced with DIRECT. Manual mode continues to expose
  only the loopback snippet for user-managed YAML.
- Verification: exercise component/path, node validation, helper readiness,
  final YAML and group-reference states with offline fixtures; run the Naive
  integration suite, POSIX checks, local-gate and diff review before any
  release. Device and remote endpoint tests remain separate evidence.

## NaiveProxy per-node health checks (2026-09-26)

- Scope: add credential-free per-node health state, bounded HTTPS probes and
  latency display inside the compatibility card. Automatic mode tests the
  exact Mihomo SOCKS5 node through its controller delay endpoint; self-managed
  YAML mode tests only the matching loopback SOCKS5 entry and reports Mihomo
  integration separately. No DNS, routing, firewall, parser or ABI behavior
  changes are included.
- Contract: every result is bound to a stable UCI node ID and current helper
  port/config generation. Missing component, listener, Mihomo node, strategy
  reference, timeout and HTTP/TLS errors are distinct states. A failed probe
  never falls back to DIRECT. Procd remains responsible for bounded local
  process respawn; health checks do not restart all OpenKill services.
- Scheduling: manual single/all-node tasks use one deduplicated backend job;
  optional periodic checks run from the existing cron boundary at a bounded
  interval (default 300 seconds), with atomic mode-600 state and expiry.
  Probe targets, redirect policy, response size and timeouts are restricted;
  credentials and response bodies are never persisted.
- Verification boundary: use offline fixtures and a local fake controller or
  SOCKS endpoint for behavior tests. No packet-path test or device/remote
  endpoint claim is made until a separately authorized device phase supplies
  evidence.

### 2026-1156 delivery evidence

- Implementation commit `348ac4bbf4c07f25adf9f06c84ebf96b722bc3a5` adds the
  stable-ID per-node health state, exact Mihomo delay checks, self-managed
  loopback probes, bounded task scheduling, expiry and credential-free UI
  diagnostics. Local health, NaiveProxy integration, UI contract/interaction/
  preview, import behavior, POSIX and CSS-pruning checks passed. The local
  `verify_3e2_safe_config.py` helper could not start because this workstation
  lacks PyYAML; the Development/RC workflows install that dependency and their
  semantic gates passed.
- Development CI for the implementation commit passed as run
  `36216779897`:
  https://github.com/dinggood615/openkill/actions/runs/36216779897
- Version preparation commit `533b460fa1212bebbe4ac7a049efe7b5caad54b6`
  advances the source metadata and release notes to `2026-1156`. Its exact
  Development CI passed as run `36217481855`:
  https://github.com/dinggood615/openkill/actions/runs/36217481855
- An initial RC Build run `36216937032` passed from the implementation
  commit `348ac4b` and was retained as a pre-version smoke artifact. The
  final-version RC Build run `36217990716` passed from `26314f2` (the
  documentation-only child of the formal source commit) and produced
  `luci-app-openkill_2026-1156_all.ipk` with SHA256
  `f9ce6831c86fe30b0010992920689ac6fe736dfd59772d0cbab12e95965d5818`.
  Its artifact ZIP is cached under
  `D:\openkill-cache\rc-36217990716` with digest
  `ea9edc510469832af945ada3375c0566b2cd89fefe7b141c8ce20d561b4be137`.
  The final candidate audit confirmed the health script is root-owned mode
  0755, the controller/view and final CSS are present, and package metadata
  reports version `2026-1156`.
- Formal Release run `36217561587` passed with `release_gate=true` and
  `publish=true` from `533b460`. Published release:
  https://github.com/dinggood615/openkill/releases/tag/v2026-1156-ipk
  targets commit `533b460fa1212bebbe4ac7a049efe7b5caad54b6` and contains
  `luci-app-openkill_2026-1156_all.ipk` with SHA256
  `e41ce2899fccb8d22dce1fb29867f5345e14238f919189a7eafeec8e615d2012`.
  The formal artifact is cached under
  `D:\openkill-cache\formal-2026-1156-artifact`; the previous release remains
  available for rollback.
- Verification boundary: no router/device, packet-path or real Naive remote
  endpoint test was run in this iteration. The fixture proves one exact
  Mihomo node can report a 42 ms delay while an independently failing node is
  reported as `mihomo-not-loaded`; it does not prove remote authentication,
  UDP, IPv6, streaming or permanent availability. Device and remote status
  remain pending a separately authorized phase.

### 2026-1157 delivery evidence

- Manual-YAML implementation commit `dfb48dbb37d666c7e443de9451eb28c6d9b3b767`
  removes new automatic Mihomo injection, preserves the legacy bridge value for
  migration reporting, keeps one protected helper instance and loopback port
  per stable node, and adds credential-free per-node probe state. The scoped
  light/dark OpenKill surface tokens are included in the final CSS. Existing
  YAML, subscriptions, strategy groups and non-Naive protocol writers remain
  outside this change.
- The exact implementation Development CI passed as run
  `36221193378`:
  https://github.com/dinggood615/openkill/actions/runs/36221193378
- Version preparation commit `2bf2321c201f67f1e91d8f8333f3c52441db465e`
  advances the source metadata and release notes to `2026-1157`. Its exact
  Development CI passed as run `36221357063`:
  https://github.com/dinggood615/openkill/actions/runs/36221357063
- The matching RC Build passed from the version commit as run `36221457511`:
  https://github.com/dinggood615/openkill/actions/runs/36221457511
  It produced `luci-app-openkill_2026-1157_all.ipk` with SHA256
  `1693212c5b19ffb7c2ea44a6f1b4a937caf703faf63a585c37de28dca59501e2`.
  The RC audit confirmed package metadata, conffile preservation, maintainer
  script safety, ownership/mode checks, stale-reference checks and the absence
  of credentials or test-machine data. The downloaded RC archive is retained
  under `D:\openkill-cache\rc-2026-1157`.
- Formal Release completed with `release_gate=true` and `publish=true` as run
  `36221712197`:
  https://github.com/dinggood615/openkill/actions/runs/36221712197
  Published release:
  https://github.com/dinggood615/openkill/releases/tag/v2026-1157-ipk
  targets the version commit and contains
  `luci-app-openkill_2026-1157_all.ipk`. The published package SHA256 is
  `954a40f3f3cf6c90ca0e57b7473b453e2b5ae4c028ad0658d76684cd0f2f74fb`.
  The RC and formal package hashes are recorded separately because the formal
  workflow rebuilds the release asset; each hash was checked against its own
  downloaded package and release checksum.
- Local evidence: NaiveProxy integration, per-node health fixtures, UI contract,
  interaction and preview tests, POSIX/BusyBox syntax checks,
  `scripts/local-gate.sh`, and `git diff --check` passed. The fixture covers
  manual-mode markers, loopback `socks5h` probing, stale-task cleanup, bounded
  state and credential absence. A local browser preview loaded the final CSS
  and showed the unified surface and aligned status cards at the desktop
  viewport; the Playwright browser runner is unavailable in this workstation,
  so the full automated multi-viewport matrix is not claimed.
- Device and remote evidence: no device, packet-path, WAN, central nft or real
  Naive authentication test was run, in accordance with the current plan and
  AGENTS.md. The release therefore does not claim remote connectivity, UDP,
  IPv6, streaming, or permanent availability. A later authorized device phase
  must re-detect the component, add a node without exposing its credentials,
  copy the generated loopback YAML, and verify the helper and probe state.
- Rollback: install the retained `v2026-1156-ipk` package and restore the
  pre-change OpenKill configuration backup before reapplying any user-managed
  YAML. Do not remove or overwrite existing release tags or assets.

### Post-release evidence update

- Evidence commit `15cc1fecf877cab0fe03651aec2fe863da669ac7` was pushed to
  `master` after the formal release to record the RC, package, browser and
  verification boundary. Its exact Development CI passed as run `36222180876`:
  https://github.com/dinggood615/openkill/actions/runs/36222180876

### 2026-1155 delivery evidence

- Source fix commit: `dcc16b54fe7a31819dbe319594eefbbdb8b6da76`;
  Development CI run `36208543045` passed:
  https://github.com/dinggood615/openkill/actions/runs/36208543045
- Version commit: `6dbd34e7ce612ad8d23db24c9b0b78f4a182a66e` (`2026-1155`);
  Development CI run `36209437647` passed:
  https://github.com/dinggood615/openkill/actions/runs/36209437647
- RC Build run `36209058686` passed from the source-fix commit. The audited
  2026-1154 candidate was retained in `D:\openkill-cache\rc-2026-1154-auto-bridge`;
  IPK SHA256 was
  `fc6072120f9ac400fa62573f8186644a6fed051c7d2df1af55c4ab3c024a4ed2`.
- Formal Release run `36209617084` passed with `release_gate=true` and
  `publish=true` from `6dbd34e`. The official release is
  https://github.com/dinggood615/openkill/releases/tag/v2026-1155-ipk and its
  package `luci-app-openkill_2026-1155_all.ipk` has SHA256
  `4393c86752319c9b73413edc432be3913048c23934da014dad6c2082fc1cd20d`.
  The published tag targets `6dbd34e7ce612ad8d23db24c9b0b78f4a182a66e`;
  the previous release and rollback asset remain intact.
- Local evidence: Naive integration, UI contract/interaction/preview tests,
  POSIX syntax checks, `scripts/local-gate.sh`, `git diff --check`, and final
  package marker inspection passed. The formal package contains the diagnostic
  state endpoint, generator stage checks, and UI status hook.
- This release has no new device or remote-endpoint run. The earlier device
  evidence below remains separate; automatic-mode internet connectivity for
  this exact release is therefore device-pending rather than claimed as fixed.

## NaiveProxy node editor runtime error (2026-09-25)

- Device phase is authorized for the supplied NaiveProxy node on
  `192.168.1.103`. The reported Add/Import actions reach the existing server
  editor, but LuCI renders `openkill/tblsection` before the editor loads.
- Scope of this fix is limited to the edit-link renderer and its regression
  contract. It must preserve the selected YAML query, stable UCI server IDs,
  node credentials and the existing add/import/manage routes. No DNS, routing,
  firewall, legacy writer, parser or bridge lifecycle behavior is changed.
- Root-cause hypothesis to verify on the device: `self.extedit:format(section)`
  interprets percent-encoded `file=` bytes such as `%2F` as extra format
  directives, producing `bad argument #2 to 'format'`. The implementation will
  replace only the explicit `%s` route placeholder and leave encoded query
  bytes untouched, then exercise add, import and manage URLs.
- Before device changes, take a protected configuration/package backup. The
  follow-up release must distinguish template rendering, form save, local
  SOCKS5 readiness and remote authentication; credentials remain off output,
  logs, reports and commits.

## NaiveProxy device node validation (2026-09-25)

- Device phase authorized by the user for `192.168.1.103` after the 2026-1149
  installation. Scope is a protected backup, redacted component/state checks,
  importing one supplied NaiveProxy node, applying the helper bridge, and
  checking the local SOCKS5 readiness and remote authentication result.
- Credentials must be sent only through the protected UCI/Naive runtime files;
  they must not appear in command output, logs, status JSON, generated YAML,
  reports or commits. Do not enable `CENTRAL_ACTIVE`, apply central nft state,
  alter WAN/default gateway, or run broad packet-path tests. Restore the backup
  if the node import or service lifecycle fails.
- Resume condition: after device evidence, repair any reproducible source
  defect locally, run all gates, publish a new version only if code changes
  are required, and record the redacted device result separately from local
  and remote endpoint validation.

### Device evidence and fixes (2026-09-25)

- Rechecked the authorized target with `ssh -o BatchMode=yes openkill-103`.
  It is Kwrt 25.12-SNAPSHOT x86_64 with OpenKill `2026-1149`; `curl`,
  `jsonfilter`, `xz` and `xz-utils` are installed.  The configured binary
  `/etc/openkill/core/naive` is executable and reports `150.0.7871.63`.
- A protected device backup was created before configuration changes at
  `/tmp/openkill-naive-backup-20260925-200732.tgz` (SHA256
  `dfb54e988cb60990d80125e9d6e13b6609969c39d1cc1085f125778e680cdf81`).
  A second protected code backup is at
  `/tmp/openkill-naive-code-backup-20260925-201140.tgz` (SHA256
  `aa949db502764af83da435ce12dc3f7f491192e9d527499b5e3e1502176a32ed`).
- Root cause 1: anonymous UCI `servers` sections were enumerated with plain
  `uci show`, yielding `@servers[0]`; the Naive helper rejected that as an
  invalid stable ID, so it reported `no-enabled-nodes` and generated no
  bridge.  The helper and init loops now use `uci -X show`.
- Root cause 2: direct helper status/prepare calls did not load
  `/lib/functions.sh`, so `config_load` failed silently outside the init
  process.  The helper now loads the OpenWrt config functions when available.
  It also reports `local_ready=1` only after every generated loopback port is
  listening.
- Root cause 3: this device's OpenWrt Naive build fails authenticated TLS when
  procd launches it as root with the `nogroup` group (`broken pipe` and
  `net_error -100`).  The Naive instance now stays in the root group; the
  change is limited to the helper process and does not alter transparent
  interception ownership.
- The supplied node was imported into one stable UCI `servers` section with
  credentials retained only in protected device configuration.  The source
  YAML was then updated with a credential-free `127.0.0.1:11080` SOCKS5
  bridge and its name was added to the existing streaming group.  The final
  active YAML contains the bridge; no credentials were written to YAML.
- Device result after the fixes: OpenKill `running`; helper state is
  `configured=1`, `generated=1`, `component_installed=1`, `local_ready=1`,
  `remote_verified=0`; the loopback listener accepted a proxied request to a
  fixed HTTPS test endpoint and returned HTTP 204.  This proves local
  process/bridge and one TCP remote request, not UDP, IPv6, streaming unlock
  or general LAN packet-path behavior.
- One temporary test invocation exposed a legacy writer hazard: running
  `yml_proxys_set.sh` while UCI has no imported groups can replace the YAML
  proxy/group arrays and make strict DNS refuse startup.  The backed-up YAML
  was restored before the final device restart, then the bridge was added
  while preserving the existing groups.  A follow-up local contract is needed
  before changing that legacy writer; no broad writer change is included in
  this device fix.
- Next action: commit the bounded stable-ID, standalone-helper, listener-state
  and root-group fixes; run gates and exact-commit CI, then use the formal
  release gate for the next version.  Device remote verification remains
  limited to the single redacted TCP probe above.

### 2026-1150 delivery and candidate-device verification (2026-09-25)

- Bounded source commit `6f02e095e523219b6312375b3703dcaa3e10f858` contains
  the stable anonymous-UCI enumeration, standalone config-helper loading,
  loopback listener readiness and device-specific root-group lifecycle fixes.
  Local NaiveProxy/UI/installer tests, POSIX checks, `local-gate` and
  `git diff --check` passed before push.
- Exact Development CI passed for that commit:
  [run 36135974228](https://github.com/dinggood615/openkill/actions/runs/36135974228).
  RC Build passed:
  [run 36136111931](https://github.com/dinggood615/openkill/actions/runs/36136111931).
  Candidate `luci-app-openkill_2026-1150_all.ipk` SHA256 is
  `0d5474c490f728247b389ebbb6757db30c8a733cd8dfc0041a9db51bfbf4d84f`.
- Formal Release passed with `release_gate=true` and `publish=true`:
  [run 36136659284](https://github.com/dinggood615/openkill/actions/runs/36136659284).
  Published [v2026-1150-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1150-ipk)
  from the same commit.  Formal IPK
  `luci-app-openkill_2026-1150_all.ipk` SHA256 is
  `49f2971a6366d770f0c96dc29f74d03d3c9c240deec60bf45a9a6061b4c74c01`;
  previous v2026-1149 remains available for rollback.
- Before installation, the device backup was created at
  `/tmp/openkill-naive-postrelease-backup-20260925-2052.tgz` with SHA256
  `bb50eecb2a9eb7d2f4e058c9cca9ea8338f84ee5615c50c1ed52c4f378a95e48`.
  The uploaded package hash matched the formal asset before `opkg` upgraded
  OpenKill to 2026-1150.  The service is `running`; the component reports
  `naive 150.0.7871.63`; the helper state is
  `configured=1/generated=1/component_installed=1/local_ready=1` with
  `remote_verified=0`.  The active and selected YAML each retain the
  credential-free loopback bridge and its streaming-group reference.  A
  fixed TCP SOCKS5 probe returned HTTP 204; UDP, IPv6, streaming unlock and
  broad LAN packet-path behavior remain unverified.
- The package-manager upgrade emitted a transient `ubus service delete`
  message while stopping the old service, but the installed package and
  service recovered and the post-install checks above passed.  The protected
  backup is the rollback path; reinstall v2026-1149 and restore that backup
  only if a configuration rollback is needed.

## NaiveProxy inline node workflow (2026-09-25)

- Scope: keep the existing server editor as the single UCI owner, but open
  its add/import/manage routes inside an accessible modal on the Compatibility
  & Auxiliary page. Move `naive_bridge_mode` into the NaiveProxy card layout
  so it is no longer rendered under the generic Other Settings card.
- Contract: the modal preserves the current selected YAML file and existing
  stable server IDs; saving, importing, enabling and deleting continue through
  the existing CBI editor. No duplicate node schema or credential endpoint is
  introduced. Closing the modal refreshes component and bridge status.
- Validation: assert that the card owns `naive_bridge_mode`, the page uses
  in-page modal buttons instead of top-level navigation links, and the legacy
  editor routes remain available. Run local UI/Naive tests and gates. Device
  and remote endpoint validation remain outside this local step.
- Implementation commit `3b6b44b2a015de89a42bfc3677e56c81252c02cc` adds the
  accessible in-page node-editor modal, keeps the existing CBI editor as the
  single credential/UCI owner, and moves `naive_bridge_mode` into the
  NaiveProxy card. Its exact Development CI passed
  ([36127049657](https://github.com/dinggood615/openkill/actions/runs/36127049657)).
- Version commit `e5f27d0b9588d2bd062ae234c620e82058b6c42a` prepared
  2026-1149 and its exact Development CI passed
  ([36127247152](https://github.com/dinggood615/openkill/actions/runs/36127247152)).
  The RC Build passed ([36127402062](https://github.com/dinggood615/openkill/actions/runs/36127402062));
  the audited candidate IPK SHA256 is
  `71e9ec0531fcad677ab3fa992a2e37fbf41723617657915944d3e4fbc7f2bc28`.
- Formal Release passed with `release_gate=true` and `publish=true`
  ([36127769222](https://github.com/dinggood615/openkill/actions/runs/36127769222)).
  [v2026-1149-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1149-ipk)
  is published from the version commit; its formal IPK SHA256 is
  `e70a905cd91cf07fedc58fca74da6f61c9d74f566d715dc392506a9cb3dfd5c4`.
  The previous 2026-1148 release remains available for rollback. Device,
  browser rendering and remote Naive endpoint validation were not performed
  in this local-only step.

## NaiveProxy automatic versus self-managed YAML mode (2026-09-25)

- Scope: add an explicit bridge mode to the existing NaiveProxy integration.
  `auto` writes credential-free loopback SOCKS5 entries into the generated
  Mihomo profile; `manual` keeps the helper and status lifecycle but only
  exposes the generated loopback snippet for a user-managed YAML file.
  Installation, DNS, routing, legacy writers, parser grammar and ABI remain
  unchanged.
- Contract: the mode is normalized to `auto` when absent or invalid. The
  generator checks the mode before injecting a bridge, while the diagnostic
  endpoint reports the same mode and continues to expose no credentials.
  Manual mode never silently becomes DIRECT and does not stop the helper.
- Validation: add integration assertions for UCI default, normalization, UI,
  generator guard and endpoint response; run local tests and gates. No device
  or packet-path validation is authorized in this local step.
- Implementation commit `abc5cab9f1023a1b3ed552d7647b35c92d5decd9` adds the
  normalized `naive_bridge_mode` field, the compatibility-page selector, the
  generator guard and mode-aware credential-free bridge status. Its exact
  Development CI passed ([36117294535](https://github.com/dinggood615/openkill/actions/runs/36117294535)).
- Version commit `6238417bc97747e1582a7659c95733f0f605eb47` prepared
  2026-1148 and its exact Development CI passed
  ([36117509671](https://github.com/dinggood615/openkill/actions/runs/36117509671)).
  The RC Build passed ([36117683662](https://github.com/dinggood615/openkill/actions/runs/36117683662));
  the audited candidate IPK SHA256 is
  `4bfe67cb58a8c7ec04fd522131a73a5c2a1e1b9475ad89b13a5fb1e05d6062c`.
- Formal Release passed with `release_gate=true` and `publish=true`
  ([36118327110](https://github.com/dinggood615/openkill/actions/runs/36118327110)).
  [v2026-1148-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1148-ipk)
  is published from the version commit; its formal IPK SHA256 is
  `559e722c090912cd7c454da13476bfb17541463ba670301c11e4d0ee1d1aa31f`.
  The previous 2026-1147 release remains available for rollback. Device and
  remote Naive endpoint validation were not performed in this local-only step.

## NaiveProxy page installation task flow (2026-09-23)

- Scope: fix the NaiveProxy component installation request chain and expose
  truthful progress. The change affects only metadata-to-install UI wiring,
  the NaiveProxy helper task state, and its LuCI endpoint; it does not change
  DNS, transparent interception, node credentials, legacy writers, or ABI.
- Contract: metadata detection remains read-only and returns a complete result
  to the caller. Installation is a single locked background task with a
  random task identifier, stage/result state, bounded log text, and polling.
  A second install request returns the existing task instead of starting a
  duplicate download. A failed replacement preserves the previous component.
- Device gate: the authorized SSH target currently timed out during the first
  recheck; package/path/dependency evidence must be refreshed before any
  device change. No device configuration or packet-path test is permitted in
  this local implementation step.
- Next action: implement the task contract, add offline behavior tests, run
  local-gate, then push the bounded change and verify its exact Development CI
  before RC and Formal Release.
- Recheck evidence: SSH access is available again. The device is running
  OpenKill 2026-1141 with `xz`, `xz-utils`, `jsonfilter`, and `curl` present;
  URL and SHA256 fields are configured, but `/etc/openkill/core/naive` is
  absent and the state file reports `component_installed=0`. The recent
  install log records a `Trace/breakpoint trap` while probing `naive.new`.
  The same configured asset and digest install successfully in an isolated
  `/tmp` directory and reports `naive 150.0.7871.63`, so the failure is in the
  synchronous request/probe path or its target attempt, not missing xz or an
  invalid digest. A protected pre-change backup is at
  `D:\openkill-device-backup-20260923-naive-task\openkill-naive-task.tgz`
  (SHA256 `ea3e089b354dcb30d1dd77af7e5a1a376e9a120556e6628a11f8a6b4c2adc43d`).
- Implementation commit `fab25321e11b3519283df033ef4a1d59da044f01` is on
  `master`; its exact Development CI passed
  ([35855847226](https://github.com/dinggood615/openkill/actions/runs/35855847226)).
  The 2026-1141 RC audit also passed
  ([35856086037](https://github.com/dinggood615/openkill/actions/runs/35856086037));
  the audited IPK SHA256 is
  `06b300390d72bf9a79f8744d3a0ce153001b86372cdb1f36fd937e468c3e6cbb`.
  Version metadata and release notes for 2026-1142 are prepared; the next
  action is its exact Development CI, Formal Release, and device candidate
  installation.
- 2026-1142 metadata commit `a219b1f848d4a16051d69563c8448d8f65b99e3b`
  passed exact Development CI
  ([35856793818](https://github.com/dinggood615/openkill/actions/runs/35856793818)).
  Formal Release passed with both gates enabled
  ([35857008078](https://github.com/dinggood615/openkill/actions/runs/35857008078));
  [v2026-1142-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1142-ipk)
  is published. The downloaded formal package is 9,226,016 bytes with SHA256
  `f6a65639935a5b336161cf80a0102b954c3a423e449d86c5c4937a2f23e1cc48`, and
  its packaged helper contains the task and polling commands.
- Device evidence after the protected backup: OpenKill 2026-1142 installed,
  the configured URL and digest remained present, and the real device task
  completed `queued → succeeded/completed`. The installed component is
  root-owned, executable, and reports `naive 150.0.7871.63`; the refreshed
  state reports `component_installed=1`, `state=disabled`,
  `reason=no-enabled-nodes`, `local_ready=0`, `remote_verified=0`. The
  OpenKill service is currently inactive because its selected `openkill`
  configuration file is absent; start attempts record `Config Not Found`.
  No node was enabled and no packet-path or remote-authentication test ran.
  The pre-install backup remains at
  `D:\openkill-device-backup-20260923-naive-task\openkill-naive-task.tgz`.
  The follow-up evidence commit `23f3a2365d0255ba1d9877a410bb45b6d7e2645f`
  also passed exact Development CI
  ([35857677654](https://github.com/dinggood615/openkill/actions/runs/35857677654)).

## Settings navigation and network card layout (2026-09-23)

- Scope: presentation-only changes to the LuCI settings navigation, card
  grouping, and responsive CSS. DNS, IPv6, TUN, access-control, traffic
  routing, UCI field names, legacy writers, parser behavior, ABI constants,
  and continuity semantics remain unchanged.
- Navigation contract: the compatibility tab keeps the existing stable key
  and UCI ownership, moves between Network & Routing and Rules &
  Subscriptions, and is labelled “兼容与辅助”. The former tab label and
  `/naive` bookmark redirect remain accepted for migration.
- Visibility contract: System Maintenance is visible by default and its
  maintenance card is expanded; the user-facing “隐藏高级设置” toggle is
  removed without deleting or renaming maintenance fields.
- Network layout contract: DNS & Local Resolution pairs with IPv6 & TUN;
  LAN/WAN Access pairs with Traffic Routing. Desktop rows stretch to their
  tallest card, while narrow viewports use one column. No fixed heights or
  network-policy changes are permitted.
- Implementation evidence: `settings.lua` now orders Network & Routing,
  Compatibility & Auxiliary, and Rules & Subscriptions in that sequence;
  `settings_theme.htm` accepts both compatibility labels for tab resolution,
  removes the advanced-settings toolbar control, keeps System Maintenance
  visible, and keeps its card expanded. Network DNS no longer promotes the
  entire card to a full-width row, so IPv6/TUN and LAN/WAN pair with the next
  cards in the shared two-column grid. `oc.css` keeps the static maintenance
  heading visually consistent with the other cards.
- Local evidence: WSL `test-installer.py` (11 tests, one environment skip),
  `test-ui-contract.py` (25 tests), `test-ui-preview.py` (2 tests),
  `git diff --check`, and `scripts/local-gate.sh` pass. The standalone browser
  probe reports `PLAYWRIGHT_UNAVAILABLE` on this host; no rendered screenshot
  is claimed from that unavailable dependency. No device or packet-path test
  was used.
- Delivery status: presentation commit
  `7ec43075375a8a69ec57a60bff8e88c89b2729a8` is on `master`. Its exact
  Development CI passed ([35847220504](https://github.com/dinggood615/openkill/actions/runs/35847220504));
  the clean jsDelivr check passed ([35847220219](https://github.com/dinggood615/openkill/actions/runs/35847220219)).
  The 2026-1140 RC Build passed ([35847382643](https://github.com/dinggood615/openkill/actions/runs/35847382643));
  its audited package SHA256 is
  `4ddba320ab058ca84a99d5012447a4dd40665a48c43b76ec569bfaf48cc3ef3f`.
  Version metadata and release notes for 2026-1141 were prepared in commit
  `7100fa8b43bf448a4cace58f28b58ca189a2e935`; its exact Development CI
  passed ([35848107679](https://github.com/dinggood615/openkill/actions/runs/35848107679)).
  Formal Release initially hit a transient upstream 403 while refreshing
  third-party resources ([35848293474](https://github.com/dinggood615/openkill/actions/runs/35848293474));
  the authorized retry passed with `release_gate=true` and `publish=true`
  ([35848616900](https://github.com/dinggood615/openkill/actions/runs/35848616900)).
  The formal package is published as
  [v2026-1141-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1141-ipk)
  and the package-channel asset
  `luci-app-openkill_2026-1141_all.ipk` has SHA256
  `e24c2d1922673402994fa5acc93853cd5a7b55f08f21af1bcad9ac3b0dbbe5f3`.
  The package channel manifest points to commit `7100fa8b43bf448a4cace58f28b58ca189a2e935`.
  A post-release RC audit from the current master evidence commit also passed
  ([35849483187](https://github.com/dinggood615/openkill/actions/runs/35849483187));
  its 25.12 SDK package SHA256 is
  `1600bb2f23ef3d0085271d9d9c26e2d52b94aa0c63361f15f32cb7837483318d`,
  with package metadata, conffile, deletion, stale-reference and sensitive
  content audits all OK.

## NaiveProxy installer archive compatibility (2026-09-23)

- Device recheck found the configured official x86_64 asset downloads
  successfully and matches the configured SHA256, but the Kwrt image has
  BusyBox `tar` without xz support and has no `xz` executable. The installer
  therefore failed while reading the `.tar.xz` archive before extracting the
  `naive` ELF. The OpenKill package did not previously declare an xz runtime
  dependency, so the UI surfaced only a generic install failure.
- Contract: the package now depends on OpenWrt `xz`; the installer decodes
  `.tar.xz` into a private temporary archive, validates member paths, extracts
  only the expected executable, then applies the existing ELF, architecture,
  loader/version probe and atomic replacement checks. Download and digest
  semantics remain unchanged, and decompressor absence is a hard failure that
  preserves the previous component.
- Device evidence before the fix: package `2026-1137` was installed and
  `naive_enabled=1`, but all approved component paths were absent and the
  helper reported `component_installed=0`, `reason=component-not-installed`.
  A direct download measured 3,397,604 bytes and matched the configured digest;
  BusyBox reported `tar: invalid tar magic` for the xz archive. The first
  2026-1138 candidate added xz and extracted the archive, but then exposed a
  second BusyBox gap: `od` is absent although `hexdump` is available, so the
  ELF architecture probe rejected the valid binary. No node credentials or
  packet-path tests were used. The corrected helper was then run in an
  isolated device directory and completed the full install path successfully,
  producing an executable whose version probe returned `150.0.7871.63`.
- A follow-up device check after installing the binary found a stale-state
  defect: the file and version probe succeeded, but `/tmp/openkill-naive.state`
  still contained the pre-install `component_installed=0` record because the
  helper's `status` action only printed the old file. This could make the UI
  report “组件未安装” after a valid manual or page-driven installation.
- The helper now refreshes the state file from the configured executable on
  every `status`, refreshes it after successful `install`, and records a
  separate `component-installed-needs-prepare` state when enabled nodes still
  require generation. Missing binaries reset only the component availability
  fields; node configuration is retained. This keeps installation, local
  entry readiness and remote verification independent.
- Local evidence after the change: `NAIVEPROXY_INTEGRATION_CONTRACT=PASS`,
  POSIX syntax, `git diff --check`, and `scripts/local-gate.sh` pass. The
  device's manually installed component remains executable at the configured
  path and reports `naive 150.0.7871.63`; its previous stale state will be
  refreshed by the updated helper.
- Delivery evidence for this fix: status-refresh commit
  `6fad2ba7ebce25fc0484a7c4517895c4d120fb9c` reached `master` and its exact
  Development CI passed ([35829223609](https://github.com/dinggood615/openkill/actions/runs/35829223609)).
  The version metadata commit `5f773dd42e0f84c50f2a3641b399b11a5344013b`
  prepared 2026-1140 and its exact Development CI passed
  ([35829445974](https://github.com/dinggood615/openkill/actions/runs/35829445974)).
- The 2026-1140 RC Build passed ([35829622739](https://github.com/dinggood615/openkill/actions/runs/35829622739));
  `luci-app-openkill_2026-1140_all.ipk` is 7,652,311 bytes with SHA256
  `c12f4724e22ab6b5fb610224c067712849322b935310e2aace98b49edbdb187d`.
  The RC audit reported package metadata, conffile preservation, maintainer
  script deletion, stale-reference and sensitive-content checks as OK.
- The authorized device was upgraded from 2026-1139 to 2026-1140 after an
  upload SHA256 match. It remains enabled and running; the configured
  `/etc/openkill/core/naive` is root-owned, executable, and reports
  `150.0.7871.63`. The updated helper reports
  `component_installed=1`, `configured=0`, `generated=0`,
  `state=disabled`, `reason=no-enabled-nodes`, `local_ready=0` and
  `remote_verified=0`. The protected `/etc/config/openkill` hash stayed
  `0bf7be81c9f5d8b959722978e8ee40c66392a2a5ee3165b2f14ed229a0dca52c`; no
  node was enabled and no packet-path or remote-authentication test ran.
- Formal Release #162 passed with both release gate and publish enabled
  ([35830055217](https://github.com/dinggood615/openkill/actions/runs/35830055217))
  and published [v2026-1140-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1140-ipk).
  The downloaded formal asset `luci-app-openkill_2026-1140_all.ipk` is
  9,224,693 bytes with SHA256
  `281bfe4204fe3744a27740c8842168a26908e29055f5e966e970f9d8cc8b8e907`;
  its packaged helper contains the xz decoder, BusyBox hexdump fallback and
  status refresh fix. The formal asset is retained separately from the
  25.12 RC package used for device validation.
- Classification: component installation and truthful status refresh are
  repaired and device-verified; share-link parsing and isolated bridge
  generation remain locally verified; a real Naive node's remote login,
  local SOCKS5 readiness and business traffic remain device-unverified.
- Next action: keep the 2026-1140 release and rollback package, and only
  begin a new versioned batch when a separately scoped defect or feature is
  authorized.

## NaiveProxy device detection and share-link import (2026-09-23)

- Device phase is authorized for `192.168.1.103` with a protected backup at
  `D:\openkill-device-backup-20260923\openkill-naive-backup.tgz`. The first
  read-only check found OpenKill `2026-1136` installed and its Mihomo process
  running, but no executable at the configured `/etc/openkill/core/naive` or
  the approved fallback locations. `naive_enabled=0`; no Naive helper was
  started and no packet-path test was performed.
- Detection contract: distinguish the OpenKill package, the NaiveProxy
  executable, node configuration, generated bridge, local listener and remote
  authentication. A missing executable must not be represented as a stale
  status-file failure, and a locally installed binary must still be marked
  unverified until its executable/version probe succeeds.
- Import contract: reuse the existing server URL importer and add only
  `naive+https://`, `naive+quic://`, and `naiveproxy://` forms. Parse with the
  existing structured URL helper, decode credentials once, map only supported
  transport fields, warn about unknown parameters, and never log or return
  credentials. Stable UCI section identity and the existing loopback SOCKS5
  bridge remain authoritative; generated Mihomo entries keep `udp: false`.
- Persistence contract: importing fills the current node editor and requires
  the normal CBI save/apply. It must not enable the helper, install a binary,
  select DIRECT, or overwrite a user policy automatically. Component
  installation remains explicit and uses the existing HTTPS/digest/ELF/
  loader/atomic replacement checks.
- Device evidence: the authorized candidate install upgraded the device from
  OpenKill `2026-1136` to `2026-1137`; the protected `/etc/config/openkill`
  hash remained unchanged, the service stayed enabled/running, and the
  configured/fallback Naive paths were absent. The helper therefore reports
  `component_installed=0`, `state=unavailable`,
  `reason=component-not-installed`; this is the expected distinction between
  the OpenKill package and the optional NaiveProxy binary. No node process or
  remote authentication was started.
- Local evidence: `NAIVEPROXY_IMPORT_BEHAVIOR=PASS`, the NaiveProxy contract,
  UI contract, UI preview, POSIX syntax checks, `git diff --check` and the
  local gate pass. The importer accepts the supported share-link schemes,
  maps IPv4/IPv6, TLS/TCP/QUIC and percent-encoded credentials, and escapes
  parameter warnings before rendering them.
- Delivery evidence: status wording commit
  `c331488644ce56e0791163bbf02135e8ae9b761e` is on `master` and its exact
  Development CI passed ([35823101717](https://github.com/dinggood615/openkill/actions/runs/35823101717)).
  The final 2026-1137 RC Build passed ([35823202127](https://github.com/dinggood615/openkill/actions/runs/35823202127)).
  Formal Release passed with the release gate and publish enabled
  ([35823541381](https://github.com/dinggood615/openkill/actions/runs/35823541381));
  it published [v2026-1137-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1137-ipk).
  The formal package `luci-app-openkill_2026-1137_all.ipk` has SHA256
  `941bbc21a9fdfc79ab91828dd65ed474384a6a28ea06c5cae0f8edcdc7ceed9e`.
  The package audit confirms version 2026-1137 and includes the status view,
  compatibility view and share-link importer. The device was upgraded to
  2026-1137 with its OpenKill configuration hash unchanged; no optional Naive
  binary or remote authentication was started.
  The follow-up evidence commit `39b9964c6902d89f165bd86e3e421322f213c722`
  is now the master tip and its exact Development CI also passed
  ([35824176728](https://github.com/dinggood615/openkill/actions/runs/35824176728)).
- Next action: if the optional NaiveProxy binary is installed on the device,
  use the new re-detect action, import a node through the existing editor,
  and separately verify the loopback bridge and remote authentication. Those
  runtime and packet-path checks remain device-scoped and are not claimed by
  this release.

## NaiveProxy compatibility unified entry and installation flow (2026-09-23)

- Rechecked baseline `452a950610a326c9bbd305845974b0fd83cc2e63` with a clean
  worktree before this change. Device access and packet-path tests remain out
  of scope for this local iteration.
- Navigation contract: the legacy `/naive` route remains a bookmark redirect,
  but no longer has a LuCI menu title. Compatibility settings is the only
  visible owner of `naive_*` fields.
- Settings/UI contract: OpenVPN exact compatibility and the NaiveProxy helper
  are ordinary cards in the same responsive two-column grid. The cards stretch
  within their active desktop row and collapse to one column on narrow layouts;
  no fixed-height or placeholder layout is introduced.
- Metadata contract: discovery is draft-only and never commits UCI. URL and
  SHA256 are treated as an inseparable asset pair; automatic fill only occurs
  when both fields are empty, preserving manual values and preventing a mixed
  URL/digest installation.
- Component contract: the compatibility card provides explicit detect, refresh,
  automatic match-and-install, install-current and remove actions. Installation
  continues through the existing HTTPS allow-list, digest/size/archive/ELF/
  loader checks and atomic replacement boundary.
- Node/bridge contract: the compatibility card links to the existing NaiveProxy
  node editor and strategy-group manager. Existing stable-section-ID port
  allocation and loopback-only SOCKS5 generation remain the source of truth;
  no native `type: naiveproxy` is sent to Mihomo and UDP remains disabled until
  separately verified.
- Local evidence: NaiveProxy integration contract, UI contract, UI preview,
  extracted JavaScript syntax check, `git diff --check`, POSIX metadata/helper
  syntax and `scripts/local-gate.sh` pass. Browser rendering, actual component
  installation, remote authentication and device behavior remain unverified.
- Delivery evidence: implementation commit
  `cdf2b6b011f26f1d520dba0a5d411c7de68f1898` and version commit
  `ba7684eadaf87aabb12beddafa758abf83054ff3` were pushed to `master`.
  Development CI passed for the implementation commit
  ([35818160394](https://github.com/dinggood615/openkill/actions/runs/35818160394))
  and the version commit
  ([35818333176](https://github.com/dinggood615/openkill/actions/runs/35818333176)).
  RC Build run 59 succeeded
  ([35818559036](https://github.com/dinggood615/openkill/actions/runs/35818559036));
  its audited candidate was `luci-app-openkill_2026-1136_all.ipk` with SHA256
  `519a0b9c42e8026c193fcff5b757078ef1f273afe0961099953e8d8a1f977292`.
  Formal Release run 160 succeeded with `release_gate=true` and
  `publish=true`
  ([35818895168](https://github.com/dinggood615/openkill/actions/runs/35818895168));
  it published `v2026-1136-ipk` and
  `luci-app-openkill_2026-1136_all.ipk` with SHA256
  `0cc3278d006027c7e67a68ee4ae3b067cb96123a9c8c1b62728df5262e3bc8ac`.
  No device installation, browser rendering or remote NaiveProxy
  authentication was performed; keep `v2026-1135-ipk` as the rollback point.

## NaiveProxy compatibility settings and metadata discovery (2026-09-23)

- Scope: move the existing NaiveProxy component controls and status actions
  into the Plugin Settings compatibility tab. The old dedicated route remains
  as a redirect so bookmarks do not create a second UCI editor.
- Settings contract: one set of `naive_*` fields is rendered by the
  compatibility CBI model. Component metadata discovery is an explicit user
  action; it may fill only empty URL/SHA256 fields and never enables nodes,
  installs a binary or restarts OpenKill implicitly.
- Metadata contract: query the official `klzgrad/naiveproxy` latest release
  API, map a detected OpenWrt CPU family to an `openwrt-*` asset, and require
  the GitHub asset `digest` before presenting an installable suggestion.
  Unknown architectures, missing digests, API errors and stale data remain
  visible as unavailable or pending verification; the source URL is never
  guessed and a source archive is never treated as an executable.
- Lifecycle contract: the existing HTTPS allow-list, size limit, archive
  traversal check, ELF architecture check, loader/version probe and atomic
  replacement remain the installation boundary. Metadata lookup only returns
  URL, digest, size, release and architecture facts. Manual values are
  preserved unless the user explicitly requests replacement.
- UI contract: the compatibility tab owns the NaiveProxy settings card and
  status/metadata controls. Desktop cards share the current two-column grid;
  long URLs, SHA256 values and errors wrap inside the card and narrow layouts
  collapse naturally. Existing Mihomo, DNS, adblock, region, RustDesk and
  OpenVPN contracts are unchanged.
- Validation plan: offline metadata parser fixtures, LuCI controller/CBI
  contract checks, final CSS/template preview, POSIX syntax and local-gate;
  no device or remote NaiveProxy session is required for this UI change.
- Working-tree validation from baseline `54726821a62d27983c200bfe531cd08457f24d7b`:
  `test-naiveproxy-integration.py`, `test-ui-contract.py`,
  `test-ui-preview.py`, JavaScript syntax check, metadata shell syntax and
  `scripts/local-gate.sh` pass. A WSL fixture run matched the official latest
  x86_64 asset and GitHub digest; unknown/missing parser paths remain
  fail-closed. No device or remote NaiveProxy session was used.
- Delivery evidence: implementation commit `b98bd34db2ccc9707976d1cb29b9423ba4ad2333`
  passed Development CI
  ([35812016741](https://github.com/dinggood615/openkill/actions/runs/35812016741));
  version/release commit `27257f5c0c28068a93ec5945b81e1a7fd09acb44` passed
  Development CI
  ([35812222147](https://github.com/dinggood615/openkill/actions/runs/35812222147)).
  RC Build
  ([35812353895](https://github.com/dinggood615/openkill/actions/runs/35812353895))
  produced `luci-app-openkill_2026-1134_all.ipk`, SHA256
  `a428acb1ba44ef9233ab02abff12583aa92fe42766fd58854fb105c13df2dc8`.
  Formal Release with both gates enabled succeeded
  ([35812770176](https://github.com/dinggood615/openkill/actions/runs/35812770176));
  published tag `v2026-1134-ipk` and package SHA256
  `6d7e61a77024722b33566651d0a62de5825341148ff916f2ddbe48738b340a2a`. No
  device installation or remote
  NaiveProxy authentication was performed; retain `v2026-1133-ipk` for rollback.

## NaiveProxy metadata tag validation follow-up (2026-09-23)

- The metadata reader now rejects release tags containing characters outside
  the safe release-name alphabet before interpolating an asset selector into
  `jsonfilter`. A malformed upstream tag therefore remains unavailable and
  cannot alter the selector expression.
- `test-naiveproxy-integration.py`, WSL POSIX syntax and `git diff --check`
  pass for this follow-up. Because this is a post-release production fix, it
  must be versioned as `2026-1135` and pass the same Development CI, RC audit
  and Formal Release gates; `v2026-1134-ipk` remains a rollback point.
- Delivery evidence: fix commit `e83415783f028f46fcbc63d243836f0b28f7bf40`
  and version commit `e4408a3f5cb477fcc1bfd7695e4c2bd2a3e7bb56` passed
  Development CI
  ([35813424031](https://github.com/dinggood615/openkill/actions/runs/35813424031)).
  RC Build
  ([35813533691](https://github.com/dinggood615/openkill/actions/runs/35813533691))
  produced `luci-app-openkill_2026-1135_all.ipk`, SHA256
  `c523565482e38538ef2260091fc8edca26d52f0d35b2d2f5e12b9240ef3d2e3f`.
  Formal Release with both gates enabled succeeded
  ([35814129021](https://github.com/dinggood615/openkill/actions/runs/35814129021));
  [v2026-1135-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1135-ipk)
  points to the version commit and its downloaded package SHA256 is
  `8abbfdd89bd0f572bd0bfb8a68e54e7ad90d76f29fa6bc5cf4e40dddb55e09a0`.
  No device installation or remote NaiveProxy authentication was performed.

## Optional NaiveProxy bridge integration (2026-09-23)

- Scope: add an opt-in official NaiveProxy helper process that exposes one
  loopback SOCKS5 listener per stable OpenKill server section. Mihomo remains
  the only transparent-takeover core; NaiveProxy never owns TUN/TPROXY/REDIRECT
  or firewall state.
- Configuration contract: UCI server section -> validated helper JSON (mode
  0600) -> loopback SOCKS5 -> generated Mihomo `type: socks5` proxy. The UCI
  section ID, not the display name, is the stable node identity and port-map
  key. Credentials never enter command-line arguments or logs.
- Lifecycle contract: component disabled or absent means no helper instance;
  configured nodes may be saved but are reported unavailable. Preparation and
  core config validation precede application. Each state distinguishes
  configured, generated, local-listener-ready, remote-unverified and failed;
  failure never silently becomes DIRECT. Stop/remove only cleans OpenKill's
  own helper files and instances.
- Component contract: installation is optional, HTTPS-only, size/digest
  checked, staged and atomically activated with the previous binary retained
  for rollback. Architecture/libc support is explicit; no invented release
  asset or unverified package is accepted.
- Network contract: bootstrap resolution follows the existing DNS/privacy
  policy with an explicit no-loop exception when required. The bridge emits
  `udp: false` until UDP forwarding is separately verified. Fake-IP values are
  not sent as ordinary real addresses to the helper. The procd instance uses
  the existing `nogroup` (GID 65534) owner return contract so helper OUTPUT is
  excluded from OpenKill's own transparent rules; no broad port or firewall
  bypass is added.
- UI contract: reuse the existing node editor, component/settings patterns and
  status cards. NaiveProxy is shown as an optional component with responsive
  two-column forms and conservative lifecycle wording; existing users remain
  disabled by default. Legacy writers, DNS policy, category order, parser
  grammar, ABI and continuity behavior remain unchanged unless a reproduced
  bridge defect requires an explicit amendment here.
- Implementation evidence in the current working tree: `servers-config.lua`
  exposes a NaiveProxy node type and isolated credential/transport fields;
  `openkill_naive.sh` validates official HTTPS artifacts, ELF architecture,
  digest, safe extraction and 0600 JSON; `yml_proxys_set.sh` emits only a
  loopback `socks5` node with `udp: false`; the init script registers one
  procd instance per stable section ID and cleans only its own state.
- UI evidence: a dedicated NaiveProxy CBI page provides component fields and
  status/install/remove actions; the runtime dashboard card reports installed,
  configured, generated, local-ready and remote-unverified states. Existing
  DNS, adblock, OpenVPN and RustDesk state cards retain their independent
  semantics.
- Local checks completed: `scripts/test-naiveproxy-integration.py`, UI contract
  (25 tests), UI preview (2 tests), POSIX `sh -n` for the helper/generator/init,
  ELF architecture fixture, Python compileall and `scripts/local-gate.sh` all
  pass. No Naive binary, remote server or device packet path was used; remote
  connection and package installation remain unverified.
- Resulting source commit `a71acf5fddabd652334e2d1f3a1bb6e1e0bfc4e2` is on
  `master`; its Development CI run `35807220865`
  (https://github.com/dinggood615/openkill/actions/runs/35807220865) completed
  successfully. No RC or Formal Release was dispatched in this local-only
  iteration because the optional binary, remote Naive server and device phase
  were not available for the required runtime evidence.
- A follow-up source fix gates generated Naive nodes on `naive_auto_start` and
  probes the staged binary with both ELF architecture and `--version` loader
  checks before activation. Commit `02e0343861b1e186f2b39adc3a7c7a0a47faba19`
  is on `master`; Development CI run `35807460581`
  (https://github.com/dinggood615/openkill/actions/runs/35807460581) passed.
- The anti-loop contract is confirmed against the existing OpenKill owner rule:
  helper instances run in `nogroup` (GID 65534), which the fw4 and legacy
  OUTPUT chains already return before interception. Commit
  `100744b67216c9100649340be106920fc63b9326` is on `master`; Development CI
  run `35807708689`
  (https://github.com/dinggood615/openkill/actions/runs/35807708689) passed.
- Release preparation advanced the synchronized source metadata to
  `2026-1133` and added version-specific NaiveProxy notes. Commit
  `ed4486d0bcb23bca7e738e5191c7c5fd2f6e8b33` is on `master`; its exact
  Development CI run `35808776516`
  (https://github.com/dinggood615/openkill/actions/runs/35808776516) passed.
  Formal Release run `35808885468`
  (https://github.com/dinggood615/openkill/actions/runs/35808885468)
  completed successfully with `release_gate=true` and `publish=true`.
  Tag/release `v2026-1133-ipk`
  (https://github.com/dinggood615/openkill/releases/tag/v2026-1133-ipk)
  points to that source commit and publishes
  `luci-app-openkill_2026-1133_all.ipk` (9,215,921 bytes, SHA256
  `E5899857D6BD3A33465F147BE62FE4A53ECC7513C426D240A9D675644D4CBBC5`).
  Existing `2026-1132` release assets remain available for rollback. No
  device installation or live NaiveProxy server test was performed in this
  local-only iteration; those runtime paths remain unverified.


## Dashboard lower-right alignment and status evidence recheck (2026-09-19)

- Baseline rechecked before changes: master `e4a61dd5113776bdde3b8d9f8db30803de5c0b98`; working tree clean; device `192.168.1.103` reports OpenKill `2026-1131`, core `RUNNING/READY`.
- Scope for this iteration is limited to the runtime dashboard layout and status evidence. DNS, adblock routing policy, region bypass, RustDesk/OpenVPN policy, startup recovery, legacy writers, parser grammar, ABI and continuity contracts remain unchanged.
- Observed layout defect: `status.htm` promotes the legacy columns into independent `.dashboard-primary-column` and `.dashboard-secondary-column` grids. The secondary metrics row is four columns by two rows, so its intrinsic height ends before the primary configuration card and leaves an unowned lower-right area.
- Layout contract: keep the existing controls and event IDs, use one shared two-column content grid, render the eight real metrics as two columns by four rows on desktop, stretch only the existing metric rows to the shared content height, and let narrow layouts collapse naturally without fixed-height placeholders or negative offsets.
- Observed status defect: the controller exposes only `adblock_dns_effective`; the state file also contains `provider_effective`, but the page cannot distinguish generated state, DNS/Core loading evidence, and actual interception verification. The adblock contract will expose both backend fields and render conservative wording when loading or verification is unknown.
- OpenVPN status wording will keep transport bypass independent: a configured compatibility switch with transport bypass disabled must state that bypass is disabled, rather than implying an applied rule.
- Planned evidence: local UI contract/preview tests, final CSS/template inspection, headless browser screenshots at supported desktop/narrow viewports, device resource/hash and status recheck after candidate install, exact-commit Development CI, RC artifact audit, and Formal Release gate.
- Local evidence completed: UI contract 25/25, UI preview 2/2, OpenVPN compatibility contract PASS, optimization test PASS, `scripts/local-gate.sh` PASS, and `git diff --check` PASS. The optimization test emits a known Windows GBK reader traceback while its isolated assertions still return `OPENKILL_OPTIMIZATION_TEST=PASS`.
- Source commit `6b82790525b1b84233428bd8a859b42b0b06c5d7` was pushed to `master`; Development CI run `35447260582` completed successfully. RC workflow run `35447349836` completed successfully from the same commit.
- RC package `luci-app-openkill_2026-1132_all.ipk` was audited (package metadata/conffile/script/sensitive-content checks passed), SHA256 `65a22e7f9960a479AC4F6B673F42276DF6C8B2D86453B93775B1D78799BC897`, with root:root ownership and executable OpenKill shell scripts.
- Device backup before RC install: `D:\openkill-device-backups\20260919-2200-rc-2026-1132\openkill-before-2026-1132.tgz`, SHA256 `465743453391D1452A53B9F4380755D29F4A9632DD9F44EF3D2C0153D71166E9`. Candidate upload hash matched; device now reports package `2026-1132`, init service enabled/running, Mihomo process present after restart, adblock `state=generated` with DNS/Core loading and interception verification explicitly `unknown/0`, and OpenVPN `reason=disabled` with `applied=0`.
- Candidate resource hashes on the device match the RC package for the final CSS, status view, controller and adblock generator. Live authenticated LuCI browser rendering and external DNS/RustDesk/OpenVPN traffic remain device-pending; no packet-path or CENTRAL_ACTIVE test was run.
- Formal Release run `35447816238` completed successfully with `release_gate=true` and `publish=true`. GitHub tag/release `v2026-1132-ipk` points to source `157085aff8ed6ee0ba4391af26babc6fac6aa626`; the published asset is `luci-app-openkill_2026-1132_all.ipk`, 9,185,972 bytes, SHA256 `1AB2858146BCD15CDB83BD26155FE4E897F9B05B4A35ACBC17B92A733F372B20`.
- Formal device backup before the final asset: `D:\openkill-device-backups\20260919-2215-formal-2026-1132\openkill-before-formal-2026-1132.tgz`, SHA256 `9678C3F8E704F202AE82683365E244E192885473A70D9F763DDE43D6DA723694`. The formal asset upload hash matched; device remains on package `2026-1132`, service running after install, Mihomo process present, final CSS hash matches the formal package, and the user configuration remains preserved.

## Runtime dashboard/layout recheck (2026-09-19)

- Rechecked `master` at the current observed HEAD before this iteration and
  confirmed the working tree is clean. The authorized device is reachable;
  `luci-app-openkill` is installed at `2026-1130`, the OpenKill init service is
  enabled and running, Mihomo is listening on the configured controller/DNS
  sockets, and the health/watchdog processes are present. Historical startup
  failures are not treated as current evidence.
- The device log review found no new OpenKill/Mihomo error in the bounded
  recent window. Older stop artifacts contain an expected `ubus service delete
  ... Not found` message from an already-absent transient object; this remains
  a lifecycle/logging item to reproduce against the current source before
  changing it. Sensitive configuration and credentials are not copied into
  this plan.
- This iteration changes only page presentation and state evidence plumbing:
  runtime dashboard DOM/grid grouping, settings-card row stretching for the
  Network & Routing tab, and any narrowly reproduced log/status defect. DNS,
  legacy writers, category priority, parser grammar, ABI, and recovery
  contracts remain unchanged unless a reproduced defect requires an explicit
  contract update here.
- Layout contract: the top Running Status, Control Panel and Mix Proxy cards
  share one three-column equal-width grid; the content/configuration and
  metrics areas use one bounded two-column grid; settings cards remain
  content-sized and stretch only within their active row, including when
  conditional fields are revealed. The page remains scoped to OpenKill and
  responsive at 1920/1366/1200/768/390 CSS px and 100%/125% zoom.
- State contract: requested, generated, applied, verified, failed and unknown
  remain independent for DNS privacy, adblock, OpenVPN and RustDesk. A state
  file, process, HTTP 200 or saved UCI value never proves network validation.
- Browser-capable local evidence: the production preview was served over a
  local HTTP origin and rendered through installed headless Chrome. At the
  1920 CSS-px capture the three top cards are equal-width and aligned, the
  content/configuration and metrics columns share a two-column boundary, and
  DNS/adblock/OpenVPN/RustDesk cards are visible. The 768 capture naturally
  uses two columns; the 390 capture has no document horizontal overflow in
  the available desktop emulation. Playwright remains unavailable, so this is
  Chrome-headless evidence rather than a Playwright run.
- Device log root cause: the configured adblock source returned HTTP 404;
  the existing script correctly failed closed but had a stale built-in URL
  (`anti-ad-domains.txt`). The source now uses the maintained
  `https://anti-ad.net/domains.txt` default and retries that source only for
  the current generation when a user source fails. Both failures retain the
  last valid cache and keep DNS privacy independent. This fallback was
  exercised after the candidate reinstall: the device state reported
  `effective=1`, `provider_effective=1` and 107600 domains, while the log
  retained a generic source-fallback warning.
- Source commit `6defd705704a109770dc2e2d7b605ba4fbf5833b` was pushed to
  `master`; the exact OpenKill Development CI run `35443784718` completed
  successfully: https://github.com/dinggood615/openkill/actions/runs/35443784718.
- The OpenVPN status correction commit `88707d37a911781eb17582175c19c59939c8885c`
  passed its exact Development CI run `35444963099`:
  https://github.com/dinggood615/openkill/actions/runs/35444963099. The
  follow-up evidence commit `8ae80f2ed03ece9c588748ae5632cc550560c332` also
  passed Development CI run `35445400459`:
  https://github.com/dinggood615/openkill/actions/runs/35445400459.
- Formal Release run `35445726210` completed successfully:
  https://github.com/dinggood615/openkill/actions/runs/35445726210. It
  published tag `v2026-1131-ipk` at source commit
  `09842b11518d9c8e61d9bca0af17cbe964fff39c` and release page
  https://github.com/dinggood615/openkill/releases/tag/v2026-1131-ipk. The
  package-channel `master/version` is `v2026-1131`; the package-channel and
  release asset are both 9,185,445 bytes with SHA-256
  `76152E9C05640E00EC29186791F7846A6478D2BA168D0437D1D53836C0D4D8B3`.
- The formal asset was uploaded to the authorized device after a fresh
  protected backup at
  `D:\openkill-device-backups\20260919-213142-formal-2026-1131\openkill-before-formal.tgz`
  (SHA-256 `B09379D801E77745275925667F12A57061389E93540CA364EE60C7EB9C3B033D`).
  Remote and local package hashes matched. The device now reports package
  `2026-1131`, preserves the existing UCI configuration (opkg staged the
  package conffile as `openkill-opkg`), reaches Mihomo readiness, keeps the
  maintained adblock list effective, and reports the corrected OpenVPN
  disabled state. The previous release and both protected backups remain
  available for rollback.
- A non-public candidate was built from the master source, normalized to
  root-owned archive members, and audited. Candidate SHA-256 is
  `0C41597BEC8919330A1DD5A343BB8267A02E26100320D544725FA2B36894A237`.
  The protected pre-install backup is outside the repository at
  `D:\openkill-device-backups\20260919-210229-ui-adblock\openkill-before-rc.tgz`
  (SHA-256 `ADC2AE1A89F4129F72EA778F21343BBB1806DC979F43D0FB66E7DE640AACE563`).
  Upload and device SHA-256 matched. After reinstall and restart, the core,
  controller, TUN/DNS, proxy listeners, firewall readiness and watchdog were
  observed; the configured user adblock URL remained unchanged. This verifies
  the source fallback and lifecycle on this device, not strict DNS traffic,
  RustDesk connectivity, OpenVPN tunnel traffic or public IPv6.

### Planned order

1. Reproduce any current device log/status defect with a protected backup and
   sanitized output; classify code, configuration, upstream or environment.
2. Rework the production status DOM/grid and settings-card layout without
   changing control IDs or CBI persistence; add/adjust focused layout and
   state-contract tests.
3. Run local UI contracts/previews/browser capability checks, shell syntax,
   local-gate, diff/diff-check, commit and push `master`, then verify the exact
   Development CI run.
4. Build and audit a non-public RC from that commit, install only after a new
   device backup, and verify page rendering, service lifecycle and state
   recovery. Packet-path, RustDesk/OpenVPN client and strict DNS traffic
   claims remain separate device gates. The candidate install and restart
   have now completed; a stop/start recovery check and final page refresh are
  still required before a release decision.
- Device revalidation also reproduced a stale OpenVPN status field when the
  compatibility toggle was on but transport bypass was off: `generated=0`,
  `reason=disabled` was paired with `applied=1`. Commit `88707d3` changes the
  writer to report `applied=0` in that branch and adds a focused contract
  assertion. Its follow-up candidate (same package version, SHA-256
  `90574A95246D969A60C7708E8F0E84468BFFB6FD42FD89E0CCF32F0AB42254ED`) was
  uploaded after an independent local hash check. The device now reports
  `generated=0`, `applied=0`, `reason=disabled` while its core and readiness
  checks remain healthy.
5. Invoke Formal Release only if all repository release gates pass; retain the
   prior tag/assets and document any unverified traffic scenarios.

### Release preparation (2026-09-19)

- The previously published source/package version was `2026-1130`; the
  repository's formal workflow requires a strictly newer source version.
  After the functional and device checks above, release preparation advances
  the synchronized Makefile, installer, README and preview version to
  `2026-1131` and adds version-specific notes. This is a release-gate change,
  not a claim that the unverified traffic scenarios have passed.

## Running status startup/UI continuation (2026-09-19)

- Scope: authorized device `192.168.1.103`, source `master`, with no
  CENTRAL_ACTIVE, central nft apply, WAN/VMware changes, or broad LAN tests.
  Device changes must be backed up, reversible, and mirrored in source before
  any candidate reinstall.
- Startup contract under review: selected UCI config path must resolve to an
  existing readable YAML; core path/architecture/execute permission must be
  checked; generation and core validation must complete before procd marks the
  service ready; every failure must clear stale runtime markers and persist a
  bounded reason. `start` return code, `enabled`, and `running` remain
  independent facts.
- UI state contract: requested, starting, running, stopping, stopped,
  disabled, startup-failed and unknown are distinct. DNS privacy, adblock,
  RustDesk and OpenVPN cards expose configured/generated/applied/verified
  independently. A state file or HTTP 200 never proves a connection.
- Layout contract: status page remains scoped to `.openkill-status-page`, uses
  content-sized grid tracks, a four-card compatibility row (DNS, adblock,
  RustDesk, OpenVPN), and a config/metrics grid with shared boundaries at
  1920/1366/1200/768/390 CSS px and 100%/125% zoom.
- ABI/continuity: do not change legacy service-port writers, DNS listener
  split, mark/routing ABI, parser grammar, or recovery semantics. RustDesk
  compatibility must not synthesize global DIRECT/port/LAN bypasses.
- Current device lead: package `2026-1130` is installed, config/core paths
  exist, service is enabled but stopped. The fresh start reached generation
  and failed before core launch because the BusyBox `ash`-embedded Ruby in
  `yml_change.sh` lost three inner double quotes, leaving no valid
  `external-controller`; this was reproduced with `sh -x` and the generated
  YAML/runtime-context check. Commit `4996744` fixes those literals and adds
  truthful RustDesk generated/applied state; `b0cf756` normalizes RC source
  ownership to `root:root` before SDK packaging. Development CI passed for
  both commits. The final RC from `6e48598` was audited and installed after
  a protected backup; the device retained its user UCI configuration and
  PassWall state.

- Local evidence: WSL runtime 28/28 (two existing skips), optimization,
  UI-contract, UI-preview, UI-interaction and local-gate pass. Playwright is
  unavailable on this host, so no browser screenshot claim is made.
- Device evidence: RC run `35441525076` passed; IPK SHA-256 is
  `64f56d6fa60a6b163bc80541e608087a9a415aa0ac62d3827b67a353cd2c130a`.
  The package archive and installed key files are `root/root` with init and
  generator mode `755`, UI/CSS mode `644`. On `192.168.1.103`, generated YAML
  reached a valid controller, Mihomo/TUN/DNS/firewall readiness passed,
  `stop` cleared the running marker and RustDesk runtime marker, and a second
  `start` returned to ready with the controller listening on `:9090`.
  No packet-path, RustDesk client or proxy traffic evidence is implied by
  startup success. Playwright is unavailable locally, so UI evidence is from
  production-template contract/preview/interaction suites, not screenshots.

CURRENT_HEAD: `6e48598` (observed master HEAD before this evidence update)
VERSION: `2026-1130`
CURRENT_PHASE: `FORMAL_RELEASE_PUBLISHED_STAGE_B_WAITING_FOR_TRAFFIC_EVIDENCE`
CURRENT_STATUS: `2026-1130 is formally published from master after the release gate; the repaired candidate passed local/CI/RC/device fail-closed checks, while proxy-dependent DNS, region, adblock, RustDesk and OpenVPN traffic behavior remains unverified`
BLOCKER: `REAL_DEVICE_GATE` — 192.168.1.103 now has a usable Mihomo core/profile and startup evidence, but no test proxy traffic, running OpenVPN tunnel/client, or RustDesk client/service details; strict DNS, region routing, adblock traffic coverage, RustDesk recovery and OpenVPN handshake remain unverified
DEVICE_STATE: `192.168.1.103` is Kwrt 25.12-SNAPSHOT x86/64 on VMware with dnsmasq 2.93, firewall4 2025.03.17~b6e51575-r2 and OpenVPN 2.7.6; the e07a983 RC is installed with configuration/PassWall preserved, OpenKill is running and OpenVPN remains untouched
DEVICE_RETRY_READY: `RC_RUN_51_DEVICE_START_STOP_RESTART_PASS` (SSH BatchMode, protected backup, candidate hash and rollback path are recorded)
NEXT_ACTION: `obtain a test Mihomo core/profile plus OpenVPN and RustDesk client/service evidence, then run only the scoped Stage-B traffic checks; do not infer packet-path behavior from the fail-closed startup result`
RESULTING_HEAD: resolve with `git rev-parse HEAD` after this status-only update; this status records the pre-commit observation above
CENTRAL_ACTIVE: `NOT_APPROVED`
CENTRAL_NFT_APPLY: `NOT_APPROVED`
REAL_PACKET_PATH: `NOT_TESTED`
DEVICE_INSTALL_AUTHORIZATION: `APPROVED_FOR_192.168.1.103_ONLY`
DEVICE_INSTALL_SCOPE: `backup, upload/install matching RC IPK, bounded OpenKill config/service tests, limited DNS/outbound observations; preserve PassWall and do not change WAN/VMware`
DEVICE_ROLLBACK_CONTRACT: `restore backed-up UCI/files, remove candidate package, restore service enable/runtime state, verify SSH; never use broad bypass or firewall reset`
IMPLEMENTATION_CONTRACTS_UNDER_REVIEW: `DNS listener split and dnsmasq stable section identity; legacy writer continuity; route-set IPv4/IPv6 atomicity and empty-set fail-closed behavior; Mihomo DNS parser/strict bootstrap; adblock DNS/core same-generation and allow/block priority; RustDesk scoped domains; OpenVPN endpoint/protocol/client-scoped transport exception; status only after validate/apply`

## Device RC evidence and follow-up (2026-09-19)

- RC Run 47 (`35436168995`) built from master `f936a3e44dfb9d0f793c23c12850908d428a1606` and passed the SDK package audit. The artifact archive is `D:\openkill-rc-candidate-f936a3e\unpack\artifact.zip`, archive SHA-256 `6932bedc7af84188b259081b0b5468943fcc4d98763706164b7c3639e8b823c7`, and the IPK SHA-256 is `88985dd1cd8fc8dc4b76bc4f93e5edfce59364663d9a1b09af35cc5f2ba1c67b`. The package audit reports metadata, dependencies, conffile preservation, maintainer-script safety, stale-reference and sensitive-content checks as passing. SDK tar entries use the normal build uid/gid `1001:1001`; device installation resolves ownership as root, so the archive owner is not treated as runtime ownership.
- A fresh protected device backup was captured at `D:\openkill-device-backups\20260919-preinstall-f936a3e\device-backup.tar.gz` with SHA-256 `B19F44160C6F3179FD1BC624C2907BD71EF16030320E94CF388C399BAA91E50A`. The candidate upload matched the local IPK hash. Standard install skipped the equal version; the explicitly authorized `--force-reinstall` installed the matching candidate without ignore-dependency or overwrite flags. PassWall configuration hash remained unchanged, and OpenKill/OpenVPN stayed stopped.
- The bounded device start/stop test returned `start_rc=0` with `last_start_failed=1` and `failure_reason=config-missing`, `running_after_start=no`; stop returned zero. nft ruleset SHA-256 was identical before/after (`6df593927d022fb66d1872e31e5b1e4f2be4f3d496437e4a6b49fd78984b5dbe`), and the OpenVPN runtime state file was removed on stop. This validates fail-closed lifecycle behavior only; no packet path was exercised.
- The installed RC helper exposed a real disabled-state defect: several branches called the uppercase symbol `OPENKILL_OPENVPN_write_state` although the function is lowercase, so state writes were silently skipped. The source is repaired and the isolated contract test now checks that every prepare fixture writes a state file. The repaired source requires a new RC build and device reinstall before the previous device result can be used as final candidate evidence.
- RC Run 48 (`35436712808`) rebuilt the repaired `b75d76da21003e906d060ce4ee030109a4b9a5da` source. Its artifact archive is `D:\openkill-rc-candidate-b75d76d\unpack\artifact.zip`, archive SHA-256 `f8dec8f742061f2e74b8216ae0472086152aec5775391b3d0a4f40a8b4fe6918`, and IPK SHA-256 `d2811e7adbd37038862ce4179abb421a22b3a0093933cd04ef124ab12e70ca07`. The repaired candidate was installed with the same controlled reinstall path; the helper hash matches, PassWall is unchanged, disabled OpenVPN preparation writes state, and the bounded start/stop check again returned `config-missing` with unchanged nft state.

## Formal release evidence (2026-09-19)

- The reviewed version commit is `ea474aeea866428d81dbde0b60d6ff0914a75009`; its exact Development CI is Run 136 (`35437049127`) and completed successfully: https://github.com/dinggood615/openkill/actions/runs/35437049127.
- Formal Release Run 153 (`35437145461`) completed successfully with `release_gate=true`, `publish=true`, and APK disabled: https://github.com/dinggood615/openkill/actions/runs/35437145461. Tag `v2026-1130-ipk` points to the version commit and the published release is https://github.com/dinggood615/openkill/releases/tag/v2026-1130-ipk.
- Published asset `luci-app-openkill_2026-1130_all.ipk` is 9,182,177 bytes with SHA-256 `c81acf2d644fa079f593e8f81f3ee0700743378d6cdf9c05efdff0676b895ea2`; package channel `master/latest-ipk.json` records version `2026-1130`, format `ipk`, architecture `all`, the same source commit and digest. The prior release remains available for rollback.
- Documentation follow-up `d0ad12b95e28adee178db8a57363141f2acec970` passed exact Development CI Run 137 (`35437486310`): https://github.com/dinggood615/openkill/actions/runs/35437486310.

## OpenVPN and UI continuation contract (2026-09-19)

- Observed source baseline before this iteration is `5725b49c7805d067fee89eb8a4e2a1becca0564f` on `master`; the worktree was clean. This section is the pre-change contract, not evidence that device behavior is verified.
- OpenVPN compatibility is opt-in and defaults off. Transport bypass is independent from tunnel-internal traffic and DNS handling.
- A transport exception is valid only when enabled and supplied with a valid endpoint set (explicit IPv4/IPv6 addresses and/or configured names), an explicit TCP/UDP protocol, and valid ports. Empty, malformed, mixed-family, or failed updates fail closed and retain the last valid runtime set.
- Router-client mode matches configured destination endpoints and ports. LAN-client mode additionally requires configured source client addresses. Server mode does not synthesize a network-wide bypass. No rule is keyed only by a global source/target port, the whole VPN subnet, all LAN devices, or all `443`/`1194` traffic.
- IPv4 and IPv6 endpoint/client sets are generated separately with staged files and runtime-safe replacement. IPv6 remains enabled; RA/ND/DHCPv6/PMTU are outside this exception. User force-proxy policy remains higher priority than this compatibility exception.
- `remote_service_bypass` and `openkill_service_ports` remain a legacy ABI. OpenVPN uses dedicated objects and cleanup only removes objects created by OpenKill. Real-IP, adblock allow-listing, DNS policy, and tunnel policy stay independent.
- Dashboard cards and compatibility settings must distinguish requested, generated, applied, tunnel-established, business-verified, and unknown states. A status file or HTTP 200 alone never proves network success. Styles remain page-scoped and content-sized.

### Planned order

1. Perform read-only OpenVPN inventory on the authorized device and recheck current source/UI state.
2. Implement the bounded endpoint generator/writer and status contract; add isolated validation, family split, atomic failure retention, priority, and cleanup tests.
3. Add compatibility settings and independent DNS/adblock/OpenVPN dashboard summaries; exercise generated DOM/state fixtures.
4. Run local-gate, diff/diff-check, commit and push the exact `master` commit, then verify Development CI.
5. Only after local and CI gates pass, build/audit an RC package and perform the previously authorized bounded device phase. Formal release still requires actual package/device evidence and the repository workflow.

### Iteration evidence (pre-commit)

- Read-only device check on `192.168.1.103` completed over the authorized SSH alias. Current facts: OpenVPN 2.7.6 (`openvpn-openssl 2.7.6-r1`) is installed; UCI contains one server and two client sections with sensitive values redacted; no OpenVPN process or `tun` interface is running; IPv4 has a WAN default route and IPv6 currently exposes ULA/link-local routes but public IPv6 was not tested. No device configuration was changed.
- The first local implementation adds `openkill_openvpn.sh`, dedicated nft/ipset endpoint/client/port objects, bounded resolver input, staged family-separated files, one checked runtime transaction, scoped rules, cleanup, UCI defaults/normalization, compatibility-page fields, dashboard summaries, and the OpenVPN adblock-domain exception. It does not enable the feature by default and does not change the legacy service-port writer.
- Isolated OpenVPN contract test passes (`14 checks`), UI contract passes (`23/23`), UI preview passes (`2/2`), and changed shell files pass `sh -n`. `scripts/local-gate.sh` passes at the observed baseline; the unified fast runner correctly refuses to report a result while the working tree is dirty and will be rerun after the bounded commit.
- Known device gate remains: there is no running OpenVPN tunnel, test client, Mihomo core/profile or usable proxy on the authorized device, so endpoint handshake, tunnel business, DNS-outbound, RustDesk and transparent packet-path behavior remain unverified.
- Official behavior references used for the contract: OpenVPN 2.7 documents `remote host [port] [proto]` and the `udp`/`tcp-client`/`tcp-server` families (including `4`/`6` suffixes); OpenWrt documents fw4 as the nftables backend from 22.03 onward and warns that manual nft rules must coexist with fw4; Mihomo documents that DNS connections follow routing rules and require an explicit `proxy-server-nameserver`. See [OpenVPN 2.7 manual](https://openvpn.net/community-docs/community-articles/openvpn-2-7-manual.html), [OpenWrt firewall overview](https://openwrt.org/docs/guide-user/firewall/overview), and [Mihomo DNS configuration](https://wiki.metacubex.one/en/config/dns/).
- The first CI run for `07d07a9` failed because the new OpenVPN setup was inside the legacy service-port writer extraction boundary. The bounded repair moved the OpenVPN setup before that writer without changing its ABI. Local shell/preflight gates and the OpenVPN/UI/DNS tests pass; exact Development CI for `b1699deee587f2f313a564ee915ef52372f9b7e3` passed in run `35432710735` (static plus both compatibility jobs): https://github.com/dinggood615/openkill/actions/runs/35432710735.
- A second local review found that a failed endpoint update could leave the old files present but omit their rules on the next firewall rebuild, and legacy `ipset restore` could flush live sets before a later bad element. The repair stages `.next` files and promotes them only after the runtime transaction succeeds; invalid or unresolved updates retain a matching role/protocol generation, and legacy backends load temporary family-correct sets before `ipset swap`. The transport protocol now accepts `tcp`/`udp` plus `tcp4`/`tcp6`/`udp4`/`udp6`, and nft/legacy rules match the selected family and protocol.
- The resulting master commit `411321b66c3ed3bb3f724b44cf2f117930f6a1db` passed the OpenVPN contract, UI contract/preview/interaction, DNS intent, optimization, shell/preflight and Linux runtime/installer fixtures (runtime 28 tests, installer 11 tests; Ruby-only cases skipped by the local host). Development CI run `35435940545` completed successfully for that exact commit: https://github.com/dinggood615/openkill/actions/runs/35435940545.

## UI recheck and status convergence (2026-09-19)

- Observed master before this iteration is `913bd2121a5642806b1d0a0648397b3a3196a920`; the working tree was clean. The device was rechecked read-only: package `luci-app-openkill 2026-1129` is installed, no Mihomo/Clash binary was found on `PATH`, and the OpenKill service state must still be interpreted from explicit return codes rather than historical notes. No device mutation is part of this UI-first change.
- The local production-template preview reproduced two UI defects. `.main-card` inherited fixed grid tracks (`--row-1-height` through `--row-4-height`), while the core status content was taller than its first track; the preview reported a 6px content overflow. The IP checker had a 35s router timeout and failure paths that called `show_querying_state()`, so a failed request could remain displayed as `Querying...` indefinitely.
- This iteration changes only the status-page presentation/state contract and the IP-check error contract. It preserves LuCI endpoint names, DNS listener split, legacy writers, category priority, Mark ABI, parser grammar, and continuity/recovery semantics. The status UI now distinguishes loading, running, stopped, disabled, startup-failed, unknown and error; IP probes converge to success, timeout or unavailable and retain the probe source/mode in the accessible label.
- The fresh device read-only check confirmed `luci-app-openkill 2026-1129` is installed, `/etc/init.d/openkill enabled` returns `0`, `/etc/init.d/openkill running` returns `1`, no Mihomo/Clash binary is on `PATH`, and no config path is currently selected. The same check showed ordinary `uci show` returns `@dnsmasq[0]` while `uci -X show` returns a stable `cfg...` section; init, adblock and watchdog now use the extended form and share one resolved ID.
- The optimization recheck fixed stable dnsmasq identity and parent/subdomain adblock precedence. Strict-DNS proxy binding, scoped RustDesk domains, IPv4/IPv6 atomic route updates, lifecycle timing and package ownership remain separately contracted; no CENTRAL_ACTIVE, central nft state or packet-path test was enabled.
- Local evidence after the changes: UI contract 23/23, preview 2/2, interaction 1/1, DNS intent 10/10, lifecycle 18/18, optimization and autonomous workflow checks passed; changed shell files pass `sh -n`; `scripts/local-gate.sh` passed at observed baseline `913bd2121a5642806b1d0a0648397b3a3196a920`. The generated preview was checked at the available 1280 CSS px viewport and reports content-sized cards with no card overflow.
- Resulting master commit `407423734c0d4d9f9b455b11bb55c1f62b580354` passed Development CI run `35429343098`: [OpenKill Development CI](https://github.com/dinggood615/openkill/actions/runs/35429343098). The follow-up RustDesk precedence fix is `f93bc254edc439c179365fa4f802bdaf2f4186e5`; its Development CI run `35429537012` also completed successfully: [OpenKill Development CI](https://github.com/dinggood615/openkill/actions/runs/35429537012). Neither commit mutates the device or contains a candidate package.
- The RustDesk fix inserts scoped user-configured DIRECT exceptions immediately before the final MATCH/FINAL rule, preserving user-specific proxy rules and keeping dynamic peer traffic under normal policy. No broad port or LAN bypass was added.
- Documentation-only follow-up commit `b094b37` is now verified by Development CI run `35429616399` with success status: [OpenKill Development CI](https://github.com/dinggood615/openkill/actions/runs/35429616399). No local code or device mutation is pending in this UI-first batch; RC build and device installation remain separately authorized stages.

## RC audit runner compatibility (2026-09-18)

- Observed master baseline before this status update is
  `f70dee5e479d6a1f92270f6eed6934e2e1ae5001`. Development CI run
  `35312752594` passed for that exact commit after the direct package Makefile
  boundary was added; the package build itself no longer expands the full
  kernel/module graph.
- RC run `35312882508` completed the direct build and produced exactly one
  `luci-app-openkill_2026-1129_all.ipk` under the SDK package feed, but its
  audit step exited 127 because the GitHub runner image does not provide
  `rg`. RC retry `35313619098` reached the same package audit after the
  runner-compatible change, then correctly rejected the package's
  `/tmp/etc/openkill` cleanup as a false positive caused by an overly broad
  substring match. Logs are retained at `D:\\openkill-rc-build6.log` and
  `D:\\openkill-rc-build7.log`.
- The bounded fixes replace only undeclared `rg` calls in the RC input,
  package and sensitive-content audits with recursive POSIX/GNU `grep` using
  equivalent file filters, and make the maintainer-script check require a
  path boundary so `/tmp/etc/openkill` remains a permitted runtime cleanup.
  They do not weaken metadata, conffile, stale reference, maintainer-script,
   CSS cache-buster or sensitive-content checks. RC retry `35314125692` then
   exposed a stale audit assumption: packaged LuCI templates use the runtime
   `<%=plugin_version%>` cache key rather than a literal version. The pending
   adjustment accepts that runtime key or the current literal version and
   requires both CSS assets. The autonomous workflow test asserts that this RC
   workflow has no `rg` dependency.
- Local evidence before the final RC: workflow contract `10/10`,
  optimization/DNS/UCI focused suites pass, `git diff --check` passes and the
  WSL `scripts/local-gate.sh` passes. The resulting commit and its exact
  Development CI run must be recorded after Git resolves the new HEAD.
- Final candidate evidence: Development CI `35314707749` passed for exact
  source commit `9f18c7bd2e7ac3c5a13ebde27f318f9b71ba0e44`; RC run
  `35314832624` passed all steps and uploaded artifact `10535040172`. The
  candidate is `luci-app-openkill_2026-1129_all.ipk`, 7,646,752 bytes, with
  SHA-256 `7cd0010c b688a449 b9f6134c dba20c72 d84b8f75 074923e1 390dadfd
  34961e99` (spaces are formatting only). The audit report confirms package
  metadata, conffile preservation, maintainer-script path safety, stale
   development-reference and sensitive-content checks. The package was
   subsequently installed on the authorized device in Stage A after a fresh
   SSH/resource/backup recheck.

## Authorized device Stage A (2026-09-18)

- The protected pre-install archive remains at
  `D:\\openkill-device-backups\\20260918-preinstall-1619f31\\device-backup.tar.gz`
  with SHA-256
  `0E49D13E3ED57D944EA09E7D4EB17778AEB710DE73D034480071A181CE0A227C`.
  SSH BatchMode access through `openkill-103` was rechecked before mutation.
- Pre-install readiness was reconfirmed: Kwrt `25.12-SNAPSHOT` x86_64,
  overlay about 789 MB free, available memory about 700 MB, PassWall global
  switch `0`, no OpenKill/Mihomo/Clash process or rule, and the stock dnsmasq
  listener on the LAN/WAN/IPv6 addresses. The candidate uploaded to `/tmp`
  matched the RC SHA-256 before installation.
- Standard `opkg install` completed for the candidate and its declared missing
  Ruby dependencies (`ruby`, `ruby-yaml`, `ruby-digest` and related packages)
  without force flags. The installed package reports version `2026-1129` and
  the candidate conffile hash. The install used about 25 MB of overlay space;
  the previous `passwall`, `dhcp`, `firewall` and `network` UCI file hashes are
  unchanged from the protected backup, and PassWall remains at `enabled=0`.
- Device shell syntax validation passed for `/etc/init.d/openkill` and all
  installed `/usr/share/openkill/*.sh` files. The capability probe reports
  `core=0` and all Mihomo protocol capabilities `unknown`; the bundled
  `oc-cn-domain.mrs` is present at 556,732 bytes. These are packaging and
  parser-readiness checks only.
- A bounded start/stop test showed the service does not claim to be running:
  the asynchronous start returned before the service reported `running`, the
  log recorded `Config Not Found` because no Mihomo profile/core exists, and
  the normal stop removed its transient service state. After cleanup there is
  no OpenKill/Mihomo/TProxy nft or `ip rule` state, dnsmasq still owns the
  stock port 53 listeners, and the OpenKill init service is not enabled at
  boot. This is a verified fail-closed startup result, not a connectivity
  recovery claim.
- Device configuration still has the package defaults (`adblock_mode=off`,
  `rustdesk_compatibility=0`, `ipv6_dns=1`). Adblock query behavior, DNS
  privacy egress, IPv4/IPv6 region decisions, and RustDesk signaling/P2P/
  relay behavior are **not verified** because no core/profile, test proxy or
  client evidence is present. Rollback remains: stop/disable OpenKill, remove
  only the candidate package, restore the protected UCI/files if needed,
  verify SSH and dnsmasq, and leave PassWall unchanged.

## Re-review and local behavior hardening (2026-09-18)

- Re-reviewed the actual `d481e444f87aa842a8893da81801ed71438d9689` source rather
  than relying on the earlier `b3fa5b6` report baseline. The nft and legacy
  region paths had separate flushes before loading the next set, and the nft
  path used hard-coded `/etc/openkill` files even when small-flash mode selected
  `/tmp`. Both are repaired. Existing sets now receive one checked nft batch or
  one ipset restore stream; a failed update returns an error without replacing
  an existing valid set. The initial missing-set case still fails closed.
- The adblock path now canonicalizes anti-AD text/Clash YAML domain payloads
  once, writes one local YAML rule-provider and one dnsmasq fragment from that
  generation, and records a source SHA-256 in `/tmp/openkill-adblock.state`.
  Allow-list domains are removed before both outputs are generated; user block
  entries are inserted before the provider. A misleading Mihomo `PASS` rule and
  the independent remote provider download were removed. MRS is not exposed as
  an effective format until the target core binary-provider ABI is verified.
  The generator now resolves the same generated dnsmasq `conf-dir` section ID
  used by the legacy writer before placing its fragment, so a second or
  reordered dnsmasq instance cannot silently receive the policy.
- Strict DNS now rejects `http://`, appends `#RULES` by structured suffix
  handling, applies the rule suffix to direct/policy resolvers, and aborts YAML
  replacement when no selectable proxy group exists. DNS bootstrap remains the
  documented direct node-resolution exception; no ordinary failure path adds
  WAN DNS or silently downgrades to plaintext.
- Added `scripts/test-openkill-optimization.py`, covering atomic update wiring,
  allow/provider semantics, strict-DNS guards and exact route validator fixtures
  for IPv4 `0/8/32`, IPv6 `::/0` and `/128`, malformed octets, and repeated
  compression. The validator fixtures pass under WSL and BusyBox `awk` on the
  authorized target (`busybox_v4=0 busybox_v6=0 bad4=1 bad6=1`). Changed
  production scripts also pass target `sh -n`.
- Focused UI/classifier suites remain green (`23/23`, `1/1`, `17/17`). The
  local policy gate passes after the repository's pre-existing CRLF typed
  semantic manifest is temporarily normalized in an isolated gate copy and
  restored byte-for-byte; the manifest itself is unchanged. No package or
  OpenKill service has been installed on the device yet.
- Pre-install backup completed on the authorized target only. Protected host
  directory: `D:\\openkill-device-backups\\20260918-preinstall-1619f31`; archive
  SHA-256: `0E49D13E3ED57D944EA09E7D4EB17778AEB710DE73D034480071A181CE0A227C`.
  The archive contains selected UCI/configuration and network baseline files;
  Dropbear host private keys were excluded. BatchMode SSH was rechecked after
  backup and PassWall remains enabled at the service layer with no OpenKill or
  Mihomo process present.
- The bounded implementation commits are `1619f315397d287cd0f7b8a8fd6ed6c7c0c22820`,
  `f3409c644e7053db4de53b2578f74f691fe8f939`, and the documentation status
  commits through `f883b70a5eff618168e1bb5aac4169435f7ddc65`. The disposable
  `codex/openkill-device-validation` branch was deleted locally and remotely;
  all delivery now uses `master`. Development CI run `35308100055` passed for
  exact commit `f65d4267d9ae0bbfe7aa046dc02d91b8ca2117f2`: static, v1.19.30,
  and latest compatibility jobs all succeeded. No device package installation
  has been attempted.

## RC package boundary repair (2026-09-18)

- Master-only delivery is confirmed: `codex/openkill-device-validation` was
  deleted locally and remotely; the only delivery branch is `master`.
- Development CI run `35309191407` passed for exact commit
  `770fee5373d3adf53afacbf7d9a3421b4321a51f` (static, v1.19.30 and latest).
  The first RC run `35308420431` and second run `35309306971` were canceled
  after fresh 25.12 SDK jobs expanded to Rust/LLVM host work (`3898` tasks)
  even with `CONFIG_USE_APK=`. Logs are retained outside the repository at
  `D:\\openkill-rc-build.log` and `D:\\openkill-rc-build2.log`.
- The RC workflow is now being narrowed to the known-good SDK boundary:
  serial `make CONFIG_USE_APK= package/luci-app-openkill/{clean,compile}`
  without top-level `-j`, followed by the existing IPK audit. This is a
  workflow-only change; it does not change production package dependencies.
- The next evidence required is a completed RC run that produces exactly one
  audited `luci-app-openkill_2026-1129_all.ipk` from the resulting master
  commit. Until that exists, no device upload or installation is allowed.

## Exact-commit DNS contract repair (2026-09-18)

- The first CI run for `f883b70` failed only in the static DNS contract suite.
  The production code had already moved to a stable `DNSMASQ_UCI` section and
  separate dnsmasq listener port, while the shadow UCI stub and lifecycle tests
  still asserted anonymous `@dnsmasq[0]` selectors and an old redirect
  placeholder. The fixture now models both selectors but returns the stable
  listener, and the source contracts assert the stable section variable.
- Local evidence after the repair: DNS intent `10/10`, UCI lifecycle `18/18`,
  optimization `PASS`, changed-script BusyBox/POSIX syntax checks, isolated
  LF local-gate `PASS`, and the full Development CI matrix `PASS` on
  `f65d4267d9ae0bbfe7aa046dc02d91b8ca2117f2`.
- This repair changes tests and the record-only harness only; production DNS
  ownership, stable-section mapping, and listener split are unchanged.

## Local optimization phase (2026-09-18)

- Phase: `PHASE_LOCAL_DNS_REGION_ADBLOCK_RUSTDESK_HARDENING`.
- Scope: local source changes only. The requested work covers stable dnsmasq
  section selection, safer IPv4/IPv6 region-pass handling, IPv6 transport
  matching, optional anti-AD Mihomo rule-provider integration, and a bounded
  RustDesk compatibility exception. No device, packet-path, CENTRAL_ACTIVE,
  or central nft operation is permitted in this phase.
- Contracts: preserve the existing DNS listener split (`dnsmasq :53` to
  Mihomo `127.0.0.1:7874`), the OpenKill/Mihomo ownership mutex, current Mark
  ABI, legacy writer continuity, and shadow read-only semantics. New adblock
  and RustDesk controls must fail closed and remain independent of DNS
  privacy and region bypass decisions.
- Implemented locally: stable dnsmasq instance identity; fail-closed and
  atomically validated IPv4/IPv6 route sets; fw4 nftset capability guard;
  extension-header-safe IPv6 protocol matching; split/strict encrypted DNS
  filtering; anti-AD DNS plus Mihomo provider rules with user exceptions;
  scoped RustDesk ID/relay domain rules; effective-state reporting in LuCI;
  and quick-start invalidation for the new generator.
- Evidence: shell syntax checks passed for all five changed production
  scripts; UI contract `23/23`, UI interaction `1/1`, classifier contract
  `17/17`, and `git diff --check` passed. `scripts/local-gate.sh` passed on
  the same source after temporarily normalizing the pre-existing CRLF copy of
  `shadow/semantic_model_v1.tsv`; the native Windows checkout otherwise fails
  its typed-manifest header check before evaluating this diff. The manifest
  was restored byte-for-byte and remains unmodified.
- Device and real RustDesk/DNS leak verification remain `NOT_RUN` until an
  explicitly approved device phase. Exact-commit Development CI is still
  pending because this local environment has not dispatched the workflow.
- Observed implementation baseline was `b3fa5b6fcdba4074b78e182516fa612a73652b7d`;
  resulting local implementation commit is
  `b3a3425c6495f7e42da1c683055a8fcfde5b6a4c`.
- Resume condition: after local gates, record the observed resulting HEAD and
  keep native takeover mappings, real DNS egress, anti-AD effectiveness and
  RustDesk relay/UDP behavior as device-validation items.

## Approved OpenWrt device phase (2026-09-18)

- Authorization: the user explicitly authorized testing the local OpenWrt
  router at `192.168.1.103` and requested direct SSH-key access. This phase is
  limited to that target; no other router or real device may be contacted.
- Initial scope: establish a dedicated local ed25519 key, install only its
  public key through the supplied administrator password, then perform
  read-only inventory, package/config inspection, service status, generated
  rule inspection, DNS listener/upstream inspection, and bounded synthetic
  configuration checks. The password must not be stored in the repository,
  command files, logs, or reports.
- Explicitly forbidden in this phase: `CENTRAL_ACTIVE`, central nft apply,
  packet-path tests, traffic capture, firewall/route/DNS mutation beyond the
  requested SSH public-key installation, package installation, service
  restart, WAN changes, and any broad bypass rule.
- Contracts under observation: DNS listener split and privacy modes, one
  transparent-proxy owner, Mark ABI, IPv4/IPv6 region-set generation and
  fail-closed behavior, adblock last-valid fallback, RustDesk scoped rules,
  and procd/legacy-writer continuity. Any mutation needed for a later test
  requires a separate explicit device step and rollback record.
- Resume condition: complete key setup and read-only preflight first; stop and
  record `HUMAN_BLOCKER` if SSH is unavailable or the supplied credentials do
  not authorize the requested key installation. Device effectiveness claims
  remain `NOT_VERIFIED` until an explicitly approved mutation/traffic phase.
- Key setup evidence: TCP/22 reachable from `192.168.1.125`; dedicated
  `openkill-192.168.1.103-ed25519` key created outside the repository with
  fingerprint `SHA256:f+jc02xQKTFS9LdSP7gtvkFF/X25W3mrEvqORuSFFjg`; Dropbear
  public-key authentication succeeded in `BatchMode` as root. The supplied
  password was used only for this one-time public-key installation and was not
  persisted.
- Local SSH convenience alias `openkill-103` now points to the dedicated key
  with `BatchMode yes`; a key-only alias connection was verified as root.
- Device read-only evidence: `/etc/openwrt_release` reports Kwrt
  `25.12-SNAPSHOT` x86/64 with Linux `6.12.103`; dnsmasq listens on LAN,
  WAN-side, Docker and IPv6 addresses; its active resolv file contains WAN
  resolver `192.168.10.2`; fw4 has only the dnsmasq UDP/53 redirect table and
  no OpenKill/Mihomo chains. The target has `dnsmasq-full` nftset support, but
  no OpenKill package, no Mihomo/Clash binary and no proxy listener.
- Device mutation record: only the dedicated public key was added for
  Dropbear access. No UCI value, route, firewall rule, package, service,
  DNS setting, or runtime process was changed by the inspection.
- Capability preflight: the target has `dnsmasq-full` nftset support, fw4/nft,
  `nft_tproxy`, `nft_socket`, `tun`, IPv4/IPv6 netfilter modules, curl/wget,
  about 789 MB free overlay space and about 978 MB RAM. These are readiness
  observations only; they do not prove OpenKill or Mihomo protocol behavior.
HOST_NETWORK_INCIDENT_CAUSE: `UNCONFIRMED`
HOST_NETWORK_SETTINGS_CHANGED_BY_THIS_WORK: `0`
TEST_PROCESS_CLEANUP: `PASS`
HOST_NETWORK_GUARD: `PASS` (the guard is fail-closed and the latest full and preflight runs saw no unexplained drift; the earlier listener-drift evidence remains historical and unattributed)
ENVIRONMENT_ERROR_CLASSIFICATION: `PASS` (required Core cases passed; `NFT_CLI_UNAVAILABLE` is explicit and bounded)
UI_STATIC_CONTRACT: `PASS`
UI_BROWSER_VALIDATION: `PASS` (local Chrome/Playwright preview at 1920/1366/768/390 CSS px, including upload mode, age-option placement, overwrite selection and editor race checks; evidence under `artifacts/test-evidence/ui-preview`)
UI_DEVICE_VALIDATION: `NOT_RUN`
UI_REFERENCE_ALIGNMENT: `PASS` (flowing two-column dashboard, full-width connectivity panel, two-column mobile metrics, truthful states and synchronized conditional panels)
IPV6_SOURCE_ROOT_CAUSE: `KNOWN_VMWARE_TEST_ENVIRONMENT_LIMITATION` (not a production defect conclusion)
CONTINUITY_CONTRACT_PRESERVED: `PASS`
WRITER_HASHES_UNCHANGED: `PASS`
FAST_GATE: `PASS` — `20260917T110207Z-2372` (18/18, no cache)
FULL_GATE: `PASS` — `20260917T110710Z-2724` (39/39; 1 explicit `NFT_CLI_UNAVAILABLE`)
DEVICE_PREFLIGHT: `PASS` — `20260917T112344Z-4584` (32/32; local readiness only, no device contact)
DEVICE_CANDIDATE_ID: `a07543025287565b341f77ce7eb1861ddf2136bd292eb5ee66c3fbfe6db03f54`
DEVICE_EVIDENCE: `artifacts/test-evidence/20260917T112344Z-4584`; latest full evidence is `artifacts/test-evidence/20260917T110710Z-2724`; historical R3B device evidence remains under `artifacts/test-evidence/r3b-device-f83d592f18b685fe62b9b94a4f907e5465ac13f3e1488a27b8bff5d1cd5ea763`
RESULTING_HEAD: resolve with `git rev-parse HEAD` after this status commit; the recorded `CURRENT_HEAD` is the pre-commit observation

IMPLEMENTED: R3C internal typed sidecar producer, canonical D2D fixture, typed ownership/DNS model, isolated staged execution, unified local gates, LuCI presentation and conditional-control fixes, T0/T1/T2 runtime-DNS continuity checks, multi-listener core-owned DNS socket selection, owned-process cleanup, and read-only host-network guarding
LOCAL_VERIFIED: focused UI/interaction suites, clean fast/full gates and clean device-preflight pass; the browser run executes production status/upload/editor coordinators at 1920/1366/768/390 CSS px with local mocks; WSL-only lifecycle changes and the explicit NFT CLI limitation are classified; the 1000-call continuity stress runs in private WSL `/tmp`; historical device cycles stopped fail-closed at IPv6 source continuity, which is deferred because `.102` is a VMware IPv6-limited test environment
DEVICE_VERIFIED: `NO` for the R3A/R3C candidate (`.102` runtime stayed healthy, but typed parity was NOT_RUN)
RELEASED: `YES` — `v2026-1129-ipk` points to `0ae5fb418514d609923a632a56250907d52a74bb`; IPK SHA256 `3017bd1569e1851105dbebceea306496fe8f7d2776aff88402bf4e1433e521d4`

The detailed phase records below are retained as historical evidence. The
single local gate runner and the hardening decisions are documented in
[`docs/dev/local-validation-hardening.md`](../dev/local-validation-hardening.md)
and [`docs/testing/TEST_GATES.md`](../testing/TEST_GATES.md).

The UI follow-up fixes stale stylesheet cache keys, the missing subscription
detail hook, status-page controls that did not recover after a later poll, and
runtime-state presentation that previously could retain a healthy-looking
chip after an incomplete or failed response. `scripts/test-ui-contract.py`
and `scripts/test-ui-preview.py` cover these source-level regressions. A local
Chrome/Playwright run exercised the production templates and CSS with mock
data; live LuCI backend and device rendering remain unverified.

The latest UI pass also covers the conditional controls that were still able
to drift after repeated interaction: dynamic CBI table tabs now update panel
visibility, selection and keyboard state together; subscription summaries keep
their base classes while toggling visibility; the overwrite editor binds its
delegated drag/touch handlers once across rerenders; and the upload editor
returns the age-encryption group to the correct mode after reset. The browser
evidence includes the production uploader/editor coordinators and an isolated
mock of these transitions. It remains local preview evidence, not live LuCI or
device validation.

## Historical execution records

## R3B self-contained typed candidate retry (blocked at device continuity)

- Phase: `PHASE_3E2D2D_R3B_RETRY_SELF_CONTAINED_TYPED_CANDIDATE`.
- The local candidate was bound to clean HEAD
  `45b94aee217c49395197a088d17f1f591c9648e6`, candidate ID
  `f83d592f18b685fe62b9b94a4f907e5465ac13f3e1488a27b8bff5d1cd5ea763`,
  and preflight evidence
  `artifacts/test-evidence/20260917T023225Z-24796`.  The staged set was
  exactly the observer, renderer, TUN template, and semantic manifest listed
  by that manifest; device-side hashes matched.  The installed 2026-1128
  observer remained unchanged.
- Only `openkill-test-102` (192.168.1.102) was contacted with
  BatchMode/IdentitiesOnly.  No .1, .101, or other device was accessed.  The
  existing runtime stayed healthy: OpenKill/procd running, one core, utun,
  IPv4/IPv6 ABI and table 354, dnsmasq :53, core UDP 7874, SSH, and the
  canonical config hash all remained valid.
- Three independent invocations of the staged automatic coordinator returned
  `STALE` (rc 6, reason `automatic-state-source`) before capture/parser or
  typed comparison.  The result was stable because the committed
  `/tmp/openkill-network.desired` and `/tmp/openkill-network.applied`
  files differ in `IPV6_PROXY_RULE`, `IPV6_TUN_ROUTE`, and
  `LOCALNETWORK6_PREFIXES`; the snapshot reports `LOCAL_IPV6_READY=1`.
  This is a source-convergence blocker, not evidence of a DNS semantic
  mismatch.  The 10-cycle gate was correctly not started.
- Post-run UCI, canonical config, installed production files, process state,
  routes/rules and service status remained unchanged.  Candidate telemetry,
  wrapper, lock and temporary directory were removed after the coordinator
  exited.  No package, UCI, nft, route, rule, reload, restart, central apply,
  or packet-path operation occurred.
- Evidence is retained under
  `artifacts/test-evidence/r3b-device-f83d592f18b685fe62b9b94a4f907e5465ac13f3e1488a27b8bff5d1cd5ea763`.
  The next action is to reconcile the stable desired/applied IPv6 source
  contract under a separately approved device maintenance step; do not rerun
  the typed comparator until continuity converges.

## R2C canonical device baseline hold (completed)

- Phase: `PHASE_3E2D2D_R2C_RESUME_WITH_CANONICAL_CONFIG`.
- Observed HEAD before and after the device run: `b8a7313a8b50afacc695d600db1a2916abddce73`; the working tree was clean and
  `566fa82` remains an ancestor.  The local chain from `455f463` through this
  checkpoint remains limited to tests, fixtures, documentation and CI; no
  production runtime, DNS, renderer, network, firewall, installer or package
  behavior changed.
- Local preflight, canonical verification, the 10-read config test, R2B's
  18/18 UCI lifecycle test, `local-gate.sh`, `ci-gate.sh`, and `git diff --check`
  passed.  The canonical source is `scripts/fixtures/3e2-safe.yaml`, 818
  bytes, SHA-256
  `9cd8d91750758823776df9c982c1e15f0baa1a72baa1792fa2f82c0df4d24a6e`.
- The only device contacted was the authorized `openkill-test-102` alias
  (192.168.1.102) with BatchMode/IdentitiesOnly.  No `.1`, `.101`, or other
  router was accessed.  The device already had package `2026-1128`; no package
  installation or UCI path write was performed.  Key production file hashes
  matched the verified 1128 package/source.
- The device began in the expected clean stopped state.  The canonical file
  was copied to `/etc/openkill/config/3e2-safe.yaml` with root ownership and
  mode 0600; device and local hashes matched.  `config_path`, `enable`,
  `dns_port`, TUN ownership/flags and other user fields stayed unchanged.
- A 300-second watchdog whose only rollback action was the formal OpenKill
  stop was armed before startup.  One controlled start reached OpenKill/procd
  running, one Mihomo process, `utun`, mark ABI `0x162/0xffffffff`, policy
  preference `1888`, table `354`, dnsmasq `:53` and Mihomo `127.0.0.1:7874`.
  A fresh SSH connection passed; the watchdog was cancelled immediately with
  rc 0, its process disappeared, no rollback marker was written, and the
  cancellation marker was present.
- The field-level UCI contract matched R2B exactly: lifecycle markers and
  dnsmasq relay/cache/AAAA state were the only expected runtime deltas;
  network UCI and `openkill-opkg` stayed unchanged, `last_start_failed` was
  absent, and no unknown delta was observed.  IPv6 main/default and
  source-specific route counts/hashes stayed stable with no NAT66 signal.
  Three 15-second read-only samples passed with identical runtime values;
  shadow remained OFF and no comparator, packet test, central apply, restart,
  or manual nft/ip/UCI operation was run.
- Success state is intentionally retained for the next phase: OpenKill is
  RUNNING, Mihomo=1, `utun` and ABI/DNS state are present, SSH is reachable,
  and the canonical config remains installed.  The next authorized action is
  `PHASE_3E2D2D_R3_PRODUCTION_SHADOW_DNS_SEMANTIC_REVALIDATION`; do not stop
  this baseline before that phase.

## R2D canonical D2D test-config provenance checkpoint (local-only)

- Phase: `PHASE_3E2D2D_R2D_CANONICAL_D2D_TEST_CONFIG_PROVENANCE_RECOVERY`.
- Observed starting HEAD: `0c2e01fd9bd298205c96d92a2f5f10f744232ed4`; the working
  tree was clean and `566fa82` remains an ancestor.  The audited commits after
  the D2C implementation contain only workflow, test, documentation, and
  release metadata changes; no production runtime, DNS, renderer, network,
  firewall, installer, parser, or ABI behavior changed.
- Device access was zero.  The earlier `.102` evidence remains frozen input;
  this recovery did not connect to `.102`, `.1`, `.101`, or any other router.
- The old R2A/R2C candidate bytes and SHA-256
  `e894c2f7918038080ca05baa1311c8d7336e2a1497ce3324b767238fe7c76b05` were
  searched for in the repository, reachable history, dangling project Git
  objects, and project test/build artifacts and were not found.  No hash
  chasing was performed, so `BYTE_EQUIVALENCE_TO_R2A=UNKNOWN`.
- A new canonical, deterministic, direct-only fixture is now persisted at
  `scripts/fixtures/3e2-safe.yaml`.  Its SHA-256 is
  `9cd8d91750758823776df9c982c1e15f0baa1a72baa1792fa2f82c0df4d24a6e`.
  `scripts/verify_3e2_safe_config.py` checks duplicate keys, binary NULs,
  sensitive/provider material, YAML structure, the frozen D2C DNS/Mark ABI
  contract, and optional Mihomo `-t` validation.  The focused regression
  `scripts/test-3e2-safe-config.py` passes 10/10 and proves one byte/semantic
  identity across ten reads.
- The fixture's semantic contract is equivalent to the frozen R2A candidate:
  TUN `utun`/`system`, OpenKill-owned `auto-route=false` and
  `auto-redirect=false`, IPv4/IPv6 and fake-IP DNS enabled, mode-1 firewall
  and dnsmasq listener `:53`, dnsmasq upstream `127.0.0.1#7874`, Mihomo
  listener `127.0.0.1:7874`, `MATCH,DIRECT`, and Mark ABI `0x162`,
  `0xffffffff`, table `354`, preference `1888`.  `53` and `7874` remain
  distinct semantic fields.  The fixture contains no credentials,
  subscriptions, tokens, private endpoints, or external provider URLs.
- The verifier passed YAML/duplicate-key/secret/semantic checks on Windows;
  official Mihomo v1.19.30 and the current latest v1.19.31 both passed `-t`
  through the existing WSL compatibility path.  The direct Windows
  invocation reports `NOT_AVAILABLE` for a Linux binary, as expected.  CI now
  installs its existing YAML test dependency and runs the verifier plus the
  focused suite.
- No production files, package version, release metadata, writer hashes, or
  device state changed.  The R2D commit is limited to the fixture, verifier,
  focused tests, CI registration, and documentation.  The prior R2C blocker
  is now specifically `CONFIG_PROVENANCE_PERSISTENCE_GAP`, not a claim that a
  human secret source is required.

### R2D result and next action

Local R2D gates and the full fixture matrix pass; the bounded change is ready
for commit.  On success, `CONFIG_SOURCE=CANONICAL_PROJECT_FIXTURE`,
`CONFIG_PROVENANCE=PERSISTED`, and `DEVICE_R2C_RESUME_READY=YES`; the next
authorized action is `PHASE_3E2D2D_R2C_RESUME_WITH_CANONICAL_CONFIG`, which is
the first phase allowed to access `.102`.  It must use this fixture and must
not rewrite production semantics.  No device or release action is taken in
R2D.

## R2C device baseline checkpoint (blocked before writes)

- Phase: `PHASE_3E2D2D_R2C_DEVICE_BASELINE_HOLD_WITH_SEMANTIC_UCI_GATE`.
- Observed local HEAD: `2592088787a8f2fce87e20e80a355d0dfec4d69c`; the working
  tree was clean and `566fa82` remains an ancestor.  The delta from
  `455f463` is limited to the R2B lifecycle test, its documentation, the
  execution-plan/test-gate records, and CI registration; no runtime, package,
  DNS, renderer, init, network, firewall, or installer source changed.
- `preflight-openkill.sh`, `local-gate.sh`, `ci-gate.sh`, and
  `test-uci-lifecycle.py` passed (18/18).  No product semantic drift was
  found after D2C.
- The only device contact was the authorized `openkill-test-102` alias using
  BatchMode/IdentitiesOnly.  Read-only evidence matched the required clean
  stopped baseline: package `2026-1128`, OpenKill inactive, Mihomo 0, no TUN,
  no OpenKill pref-1888/table-354 state, no 7874 listener, the configured
  target `/etc/openkill/config/3e2-safe.yaml` absent, shadow unset, and the
  existing UCI path/hash intact.  Key production file hashes matched the
  current 2026-1128 source.
- The R2C hard configuration gate cannot be satisfied from the project
  source: no approved `3e2-safe.yaml`, generator output, tracked-history file,
  or project-generated copy matching
  `e894c2f7918038080ca05baa1311c8d7336e2a1497ce3324b767238fe7c76b05` exists.
  The device's leftover generated `/etc/openkill/3e2-safe.yaml` is a different
  hash and is not an approved, secret-free candidate; it was not reused.
- Result: `CONFIG_RECONSTRUCTION_DRIFT`.  The run stopped before transfer,
  package installation, configuration materialization, service start, UCI,
  nft, route, rule, DNS, network, or reboot writes.  The next resume requires
  an exact approved candidate (or a committed deterministic generator) and a
  re-run of the local hash/validation gates before any device write.

## R2B local UCI lifecycle checkpoint (observed before this change)

- Phase: `PHASE_3E2D2D_R2B_LOCAL_STARTUP_UCI_MUTATION_CONTRACT_RECONCILIATION`.
- Observed starting HEAD: `455f46309e30b7931cc2598bb16bfef5fc7ae688`;
  working tree clean; `566fa82` remains an ancestor. Devices were not accessed.
- The R2A whole-file running hash gate was too strong.  The checked-in start
  path intentionally records reversible dnsmasq backups, runtime/fallback
  metadata, a transient failure marker, one-shot overwrite state and the
  firewall include; the DHCP package receives the corresponding dnsmasq
  redirect.  Formal stop restores the reversible fields, converges lifecycle
  markers to their inactive value and intentionally retains resolver backup
  metadata, which is the convergence boundary.
- A field-level contract is now covered by `scripts/test-uci-lifecycle.py` and
  `docs/dev/phase-3e2d2d-r2b-uci-lifecycle.md`.  The full local matrix and
  Development CI include that focused suite.  The contract keeps user fields and a
  target-present `config_path` unchanged, requires exact OpenKill/DHCP runtime
  deltas, rejects unclassified writes, and requires stop convergence.
- Local verification for this checkpoint: `scripts/test-uci-lifecycle.py`
  passes 18/18; `test-autonomous-workflow.py`, the Development CI static suite,
  WSL runtime/installer/network/snapshot/Stage-D/core suites, `local-gate.sh`,
  and `git diff --check` also pass.  Shell-dependent suites report their
  expected Windows entry-point failures when invoked directly and pass through
  their WSL entry points.  No production behavior, version, release, or device
  state is changed.

### R2B next action

After the local gates pass, commit only this lifecycle contract/test/documentation
change.  `R2A_CAUSE=VALIDATION_GATE_MODEL_DEFECT`; no production UCI lifecycle
defect is currently evidenced.  The next authorized phase is
`R2C_DEVICE_BASELINE_HOLD_WITH_SEMANTIC_UCI_GATE`, which requires a separately
approved device run; this phase does not perform it.

## Final delivery checkpoint (observed before this documentation commit)

- Release candidate source: `c1e6cb1c55e7166040cc231f3a2c152e7cb14a1d`.
- Source version: `2026-1128`; reviewed notes: `docs/release/notes/2026-1128.md`.
- Exact-commit Development CI: run `34981702407` passed.
- Formal Release workflow: run `34981791062` passed with
  `release_gate=true`, `publish=true`, and `build_apk=false`.
- Published tag: `v2026-1128-ipk`, targeting the release-candidate commit.
- Published asset: `luci-app-openkill_2026-1128_all.ipk`, SHA-256
  `0581360bf8d88cbf2d49b8dae1c59b3cec5be44108f1fa6fca79c4e32e1ebedd`.
- Package channel `package:master/version` reports `v2026-1128`, and
  `master/latest-ipk.json` points to the same commit, asset and digest.
- Historical `v2026-1127-ipk` and its asset remain present and unchanged.
- Release transport requires version-specific reviewed notes and preserves
  existing tags/releases; development pushes do not publish.
- Device validation remains pending and was not accessed; CENTRAL_ACTIVE,
  central apply and packet-path testing remain forbidden/pending.

The resulting documentation checkpoint must be verified from Git after commit;
the commit hash is intentionally not predicted here.

## Current authorization and acceptance

The user authorized continuing unfinished local development through an explicit
RELEASE_GATE and GitHub publication. This supersedes the historical stop at
RELEASE_GATE below. Devices remain forbidden. Do not enable CENTRAL_ACTIVE,
apply central output, run packet tests, force push, delete tags/releases, or
overwrite unknown work. Device-dependent product work is deferred, not passed.

Observed starting HEAD: de9e27b09436e8441c6668e73d391d12e320df02; clean master.
Exact-commit Development CI passed: run 34977615717.

## Bounded delivery work

1. Audit post-D2C contracts and release transport. D2C local DNS reconciliation
   is already implemented; do not invent another DNS behavior change.
2. Fix release transport: preserve existing releases/tags and require reviewed
   version-specific notes before publication. Test missing-note failure before
   any external mutation and retained manual release gates.
3. Run the full local fixture matrix with supported Windows/WSL entry points,
   the local gate, and exact-commit Development CI; repair failures.
4. At RELEASE_GATE, select the next unused source version, update the three
   version authorities, and disclose unverified device behavior in notes.
5. Commit/push, verify exact-commit CI, explicitly dispatch the formal IPK
   release, verify downloaded asset SHA256 and package channel source identity.
6. Record outcome and stop after verified delivery. No automatic Phase 4.

## Remaining device-only gaps

Post-D2C actual-device semantic parity remains PENDING. Local frozen fixtures
cannot close it. TUN BC-04 remains the documented CURRENT behavior; Access
and TPROXY device coverage remain NOT_OBSERVED. REAL_PACKET_PATH=NOT_TESTED.
The release retains legacy writer authority and default-off shadow. These
limitations are mandatory release notes, not evidence of device readiness.

## Historical checkpoints (authorization below has been superseded)

# Current execution plan: post-D2C autonomous activation

## Active checkpoint

- Observed local and remote HEAD at activation: `43c1c45e32c63a9a62b3701caca8b7c33471bdaf`.
- Branch: `master`; clean at activation; origin verified through GitHub API.
- Resolve current HEAD with `git rev-parse HEAD` at every restart. The observed
  hash above is a baseline, not a claim that later checkpoint commits are stale.
- Migration: PASS. AUTONOMOUS_ACTIVATION=PASS.
- Current phase: post-D2C local/CI closure; executor STOPPED_AT_REAL_DEVICE_GATE.
- Latest verified implementation HEAD: `6f98a0966a339796b58b9e047d577f931a0db74d`.
- Development CI: PASS, run 34977442249 for that exact implementation HEAD.
- This documentation checkpoint is a descendant commit. Resolve its actual
  HEAD from Git and check its own CI on restart; do not recursively rewrite
  this file just to embed its own commit hash.
- Baseline Development CI: PASS, run 34974224074 for the observed hash.
- Branch protection: absent (GitHub API); this executor must enforce gates
  before pushing. Repository-side enforcement remains a known limitation.
- Version before this release gate: `2026-1127`; the authorized release candidate
  is `2026-1128`. No device access or Phase 4 writer handoff is authorized.

## Next autonomous action

REAL_DEVICE_GATE: post-D2C real-device semantic revalidation is required
before advancing the product toward Phase 4. No device access is authorized
in this execution. Local fixtures do not prove current device parity.

On restart, read AGENTS.md and this file, inspect HEAD/worktree and verify
Development CI for that exact HEAD. Repair any ordinary CI regression locally.
If CI is green and no new local work item exists, retain this gate and stop;
do not invent feature scope or repeatedly commit unchanged status.

Resume product development only when the user explicitly authorizes the
post-D2C device phase with a target and scope, or supplies a concrete local
work item. Central apply/packet-path work and RELEASE_GATE remain separate.
No unattended executor or recurring wakeup is claimed to be running while
this gate is active. Repository restart instructions are persisted and the
first autonomous local iteration and its CI repair have been completed.

## Activation implementation

- Development, RC and formal Release triggers/permissions inspected. Only
  the manual formal workflow can publish OpenKill packages; it requires both
  release inputs. No workflow has been dispatched by this activation.
- Development CI now runs the local gate and ten additional portable contract
  suites. Windows/WSL-specific regressions remain a required local matrix.
- Ordinary failures repaired: document Linux entry points for installer,
  runtime, network, snapshot and Stage D; isolate Stage D from host fw4 state
  with a record-only nft CLI, verifying check-only calls, error propagation
  and destructive-batch rejection. Production semantics remain unchanged.
- Core compatibility passed locally for v1.19.30 and latest resolved v1.19.31
  (8 TUN configuration cases per core; loopback API/auth, proxy and DNS smoke).
- No live router, central apply, version change or publication was performed.

## Historical migration baseline

- Repository: `D:\openkill`
- Branch: `master`
- HEAD: `1a9678bc99745fe6183fac92e0ad4995e36c384e`
- Working tree: clean at migration start
- Remote: `origin` → `https://github.com/dinggood615/openkill.git`
- Source version: `2026-1127`
- Historical release: `v2026-1127-ipk` (published by the former push-triggered
  workflow; retained as incident evidence)

The repository did not previously contain a project `AGENTS.md` or a
`docs/exec-plans/CURRENT.md`; this file establishes the missing source of
truth for autonomous work.

## Frozen product evidence

The local 3E.2D chain is complete through D2C: continuity and coherent
snapshot, BusyBox normalization and byte preflight, Mark ABI mapping, CURRENT
renderer, bounded parser, conditional inventory classification, ownership
projection, and DNS field reconciliation. The historical device target was
`.102`; this recovery performs no device access.

- D2A: required absence fails closed; conditional/inactive absence reaches the
  comparator.
- D2B: legacy-only WAN safety remains observed but out of CURRENT-owned parity;
  DNS fields are typed and 53 is never equated to 7874.
- D2C: the checked-in mode-1 contract is firewall/dnsmasq `:53` forwarding to
  Mihomo `127.0.0.1:7874`; direct mode-2 remains separate.
- Known gaps: device revalidation after D2C, documented TUN BC-04 behavior,
  access overlap not observed, TPROXY not observed, and no central apply or
  packet-path approval.

## CI recovery

The old compile workflow ran on every `master` push. Its first run after the
D2C commit failed because source `2026-1126` equaled the already published
channel version. The source was advanced to `2026-1127`, the package rebuilt,
and the release succeeded. This exposed the process defect: development pushes
could publish. The migration changes make development CI, manual RC build,
and manual formal release independent.

Latest known CI before this recovery: development validation, runtime matrix,
package compilation, publication, and cache cleanup all passed for
`1a9678b`; the published IPK digest was
`07723684b420b0f5c949f519cca06f91f115184d21ee6ae0354bf41494905b15`.

## Historical migration work items (completed)

1. Add the repository agent guide and execution-plan source of truth.
2. Separate development CI, artifact-only RC builds, and formal releases.
3. Add dependency-light preflight, local-gate, and CI-separation helpers.
4. Run the full local matrix and inspect the final diff.
5. Commit only these migration changes, push them, and verify development CI.

Do not bump the version, publish a release, access a device, continue Phase 4,
or change product semantics as part of this plan.

## Recovery result

The migration work is limited to workflow, documentation, and dependency-light
local gates. `OpenKill Development CI` is the only push/PR path; the RC build
is manual and artifact-only; the formal release is manual and requires both
release inputs. The source version remains `2026-1127` and no release was
published by this recovery.

The local gate, workflow contract tests, shell/YAML/version validation, core
compatibility matrix, installer, runtime, renderer, parser, shadow,
continuity, network, snapshot/FW4, Stage D, classifier, semantic, NFT IR, and
central-wiring suites pass under their supported Windows/WSL entry points.
The nft syntax suite also passes its explicit unavailable-tool contract when
the host cannot execute `nft`; no package was installed to change that result.
The only expected local skips are the existing Ruby-dependent tests.

No device or router was accessed. The historical `v2026-1127-ipk` publication
remains retained as incident evidence; this recovery does not delete, alter,
or republish it.

## Local activation result

- FULL_LOCAL_GATE=PASS: 343 tests across 22 fixture suites, with the three
  existing Ruby-dependent skips (installer 1, runtime 2); both core smoke
  matrices also passed. Per-suite logs remain local under `work/*.log`.
- The Windows nft-syntax suite passed its unavailable-CLI contract; it did
  not perform real parsing there. The shell-renderer suite passed its WSL
  check-only nft matrix. Neither result is live-device validation.
- Workflow/source gate and diff whitespace review passed. Source version
  remains 2026-1127. Implementation commits are pushed and exact-commit CI passed as recorded above.

## CI repair iteration

Activation commit `ee282e36b59b26df778c26ae38757ca8b71bc341` reached CI
run 34977232002. Its new network suite exposed a fixture dependency on the
runner's DNS servers. The repair supplies a documentation-range resolver and
stubs nslookup/resolveip so the existing getent fallback and timeout-preserves-
old-state assertions run deterministically without live DNS. This changes
only the test environment. The repaired commit passed CI run 34977442249; the gate can close.

## Closure evidence

- Implementation commits: `ee282e3` (activation and Stage D isolation),
  `6f98a09` (DNS fixture isolation); both pushed to origin/master.
- Passing run: https://github.com/dinggood615/openkill/actions/runs/34977442249
- Working tree was clean before this documentation-only checkpoint.
- REAL_DEVICE_VALIDATION=PENDING; RELEASE_GATE=NOT_REQUESTED.
- No version bump, package publication, tag change or real-device access.

## Phase 3E.2D2D-R3 — production shadow DNS semantic revalidation

Observed on 2026-09-16. The source baseline was `1f9b3ef78cce76b47993b2339aa96751412de90e`, version `2026-1128`, with a clean worktree. The D2C commit `566fa82f0b814710b290c4bbd7e2385b689bd616` is an ancestor. The complete chain from `455f46309e30b7931cc2598bb16bfef5fc7ae688` to this baseline contains only workflow, fixture, test, and documentation changes; production runtime, init, renderer, parser, network, firewall, shadow wiring, installer, package, and version semantics are unchanged.

Only `openkill-test-102` (`192.168.1.102`) was accessed. No other router or device was connected, read, or modified. The existing R2C baseline remained running throughout: package `2026-1128`, OpenKill/procd running, one `/etc/openkill/clash` core process, `utun`, rules `1888: fwmark 0x162 lookup 354` for IPv4 and IPv6, one route in table 354 for each family, dnsmasq on `:53`, core listener `127.0.0.1:7874`, and canonical fixture SHA-256 `9cd8d91750758823776df9c982c1e15f0baa1a72baa1792fa2f82c0df4d24a6e`. Shadow remained disabled in persistent state and the canonical configuration hash was unchanged after the run.

The approved production entrypoint was `/usr/share/openkill/openkill_nft_shadow.sh:openkill_shadow_compare_nft`, reached through the init `openkill_shadow_stable_boundary`. It was activated only with an ephemeral `OPENKILL_NFT_SHADOW=1` environment and the existing read-only state/scalar inputs; no UCI, service, network, nft, route, rule, DNS, package, or central-apply operation was used. The coordinator performed its normal continuity snapshot, bounded capture (25 chains and 23 sets), parser, inventory classification, CURRENT renderer, directional compare, T2 continuity check, and bounded telemetry publication.

The first formal cycle returned `MISMATCH` (`rc=1`), not a capture, parse, stale, or command error. Four more independent official coordinator cycles produced the same result: 5/5 `MISMATCH`, 0 capture/parser errors, 0 stale results, 0 unknown syntax, and stable continuity identity `8f995a094bcf`. Inventory evidence retained all 24 absences as `required=0`, `conditional=22`, `inactive=0`, `optional=0`, `out_of_scope=2`, `unknown=0`; D2A classification therefore passed. Because the first cycle was not a complete MATCH, the 10-cycle success gate was not run.

The frozen typed DNS facts are still the D2C contract: actual and desired firewall LAN/router targets are `53`, dnsmasq listen is `53`, dnsmasq upstream is `127.0.0.1#7874`, and the core listener is `127.0.0.1:7874`; `53` and `7874` remain distinct fields. IPv4/IPv6 DNS scope is LAN plus router, SKGID loop prevention is `!=65534`, and the mark ABI is `0x162/0xffffffff`, table `354`, preference `1888`. The raw production result cannot publish these typed fields because its shell comparator still compares normalized chain/rule subsequences.

Bounded diagnostics attributed the stable mismatch to the production comparator model, with no device fix attempted:

- `WAN_SAFETY`: the actual-only `openkill_wan_input` and `openkill_wan6_input` reject rules are formally `OUT_OF_SCOPE_LEGACY_OBJECT`, but the shell comparator's `owned_chain()` treats every `openkill*` chain as owned.
- `DNS`: the actual `nat_output` IPv4/IPv6 `skgid != 65534` redirects to `:53` are physically consistent with the typed mode-1 path, while the CURRENT renderer expresses the path through the DNS jump/redirect topology; the shell comparator has no typed DNS or chain-transitive model.
- `POLICY_TOPOLOGY`/`OTHER`: additional legacy imperative spellings (mark formatting, protocol normalization, fake-IP/set references, and related chain forms) are stable raw topology differences, not evidence of a device renderer failure.

Accordingly, the phase result is `PARTIAL`: `FRAMEWORK=PASS`, `CURRENT_OWNED_PARITY=MISMATCH` for the official production path, and `DNS_PARITY=COMPARATOR_MODEL_GAP` for the typed interpretation. The device result is `DEVICE_SEMANTIC_MISMATCH` pending a local production-shadow ownership/DNS model integration. No 53/7874 equivalence, whitelist, fixture rewrite, parser change, renderer change, ownership deletion, or device hotfix was introduced.

Post-shadow health stayed PASS. All production-write counters were zero: nft configuration, routes, rules, UCI, network/firewall/fw4 reloads, dnsmasq/core/OpenKill restarts, package/config writes, central apply, and packet tests. Only bounded shadow temporary/telemetry files were created and then removed; no shadow process, lock, or temporary directory remained. The eight frozen writer hashes are unchanged. Canonical verification, the 10-case config suite, the 18-case UCI lifecycle suite, `local-gate.sh`, `ci-gate.sh`, `validate-openkill.sh`, and the focused production-shadow suite passed in their supported local environments. Linux-only or real-nft checks that cannot run under this Windows/WSL host remain environment-limited and are not treated as device evidence; no new unexplained skip was added.

`NEXT=PHASE_3E2D2D-R3A_LOCAL_PRODUCTION_SHADOW_OWNERSHIP_DNS_MODEL_RECONCILIATION` (local only; resolve the typed ownership/DNS projection before another device run). `CENTRAL_ACTIVE=NOT_APPROVED`, `CENTRAL_NFT_APPLY=NOT_APPROVED`, and `REAL_PACKET_PATH=NOT_TESTED` remain unchanged.

## Phase 3E.2D2D-R3A — local production shadow ownership/DNS model reconciliation

Observed on 2026-09-16 from baseline `34eebdca4d7f036cfe63c3931a6a0fee7951a55c`, version `2026-1128`, with a clean worktree before the R3A change. The D2C commit `566fa82f0b814710b290c4bbd7e2385b689bd616` remains an ancestor. No device or router was accessed in this phase.

R3's stable `MISMATCH` was reproduced as a comparator model gap. The old automatic shell comparator selected `nat_output` and every physical chain beginning with `openkill` through `owned_chain()`. That syntax scope was useful for bounded parsing but was being used as policy, so the legacy-only `openkill_wan_input` and `openkill_wan6_input` safety objects entered CURRENT equality. The same path compared raw chain/rule topology and had no independent DNS projection, even though the frozen actual and D2C desired DNS facts agree. This is `R3_CAUSE=PRODUCTION_COMPARATOR_MODEL_GAP`, not a device DNS defect.

R3A adds an additive, bounded typed path to `openkill_nft_shadow.sh`. The production shell reads the checked-in `shadow/semantic_model_v1.tsv` vocabulary and two line-oriented `OPENKILL_SHADOW_TYPED_INTENT_V1=1` sidecars produced from the completed capture/inventory and CURRENT renderer projections. Logical IDs, component, ownership class, active state, and semantic payload are compared; physical names are retained for full observation only. `CURRENT_OWNED` and active `CONDITIONAL_CURRENT` enter equality. `LEGACY_ONLY_SAFETY`, `FW4_BASE`, `INACTIVE_MODE`, `OPTIONAL_OBSERVATION`, and `OUT_OF_SCOPE` remain observed and hashed but are excluded from CURRENT-owned equality. `UNKNOWN`, invalid or duplicate rows, and missing typed DNS sources return the additive `MODEL_GAP` status (`rc=12`); the existing MATCH/MISMATCH/STALE/capture/render result numbers are unchanged.

The typed DNS projection keeps these fields independent: firewall LAN target, firewall router target, dnsmasq listen target, dnsmasq upstream target, Mihomo listener, loop prevention, IPv4 scope, and IPv6 scope. The D2C mode-1 values are firewall/listen `53`, upstream `127.0.0.1#7874`, and Mihomo `127.0.0.1:7874`; mode-2 direct behavior remains represented separately. No `53 == 7874` or transitive service equivalence was added. Each field carries a source description and owner, and a missing source is `MODEL_GAP` rather than an inferred value.

The shell path emits bounded model/version fields, short full-observation/current-owned/DNS hashes, parity, and counts only. It remains POSIX `/bin/sh` and BusyBox compatible with no Python, jq, Ruby, or other new runtime dependency. `openkill_shadow_semantic_model.py` is a development oracle only; differential tests compare its result with the shell path. The old raw automatic and explicit-bundle paths remain available for existing callers, while the typed production caller must provide both formal sidecars from the same coherent snapshot cycle.

Local evidence: the production coordinator replay with the sanitized R3/D2C fixture is `FRAMEWORK=PASS`, `CURRENT_OWNED_PARITY=MATCH`, `DNS_PARITY=MATCH`, `MODEL_GAP=NONE`; WAN safety observation is retained. The 14-case production typed-shadow suite passes; five positive shell cycles are stable (`MATCH=5/5`, one actual-owned hash, one desired-owned hash, one DNS hash pair), and the negative matrix is stable for three repetitions and distinguishes MISMATCH from MODEL_GAP. The Python oracle and shell result agree. D2A required/conditional absence behavior, D2B ownership projection, D2C DNS fields, R2B UCI lifecycle, canonical config, parser, renderer, IR, syntax, continuity, auto-state, BusyBox, network, snapshot/FW4, Stage D, runtime, installer, Core compatibility, local-gate, ci-gate, compileall, and diff-check pass in their supported local environments. Existing Ruby-dependent tests remain the only expected host skips; no new unexplained skip was introduced. `nft-c` was exercised where available and remains an environment-specific check in suites that cannot invoke it on this host.

Production impact is limited to the shadow observer/comparator and its additive manifest/telemetry: `PRODUCTION_SHADOW_OBSERVER_CHANGED=YES`, `PRODUCTION_LEGACY_WRITER_CHANGED=NO`, `DNS_WRITER_CHANGED=NO`, `ROUTING_WRITER_CHANGED=NO`, `FIREWALL_WRITER_CHANGED=NO`, `DATAPLANE_WRITE_BEHAVIOR_CHANGED=NO`, and `CENTRAL_WRITE_CALLSITE=0`. The eight frozen writer hashes remain unchanged. No version, package, release, tag, or workflow publication changed.

`PHASE_3E2D2D-R3A=PASS`; `LOCAL_R3_REPLAY=MATCH`; `PRODUCTION_TYPED_OWNERSHIP=READY`; `PRODUCTION_TYPED_DNS=READY`; `DEVICE_REVALIDATION_READY=YES`. The device phases remain partial until a separately approved device run consumes typed sidecars. `NEXT=PHASE_3E2D2D-R3B_DEVICE_PRODUCTION_SHADOW_TYPED_REVALIDATION`. `CENTRAL_ACTIVE=NOT_APPROVED`, `CENTRAL_NFT_APPLY=NOT_APPROVED`, and `REAL_PACKET_PATH=NOT_TESTED` remain unchanged.

## Phase 3E.2D2D-R3B — device typed-shadow revalidation gate

On 2026-09-16 the R3B preflight used source baseline
`0708ba5480c6c4507b1eba7acdfc00e8fd67891a`, version `2026-1128`, with a
clean worktree and the D2C ancestor check passing. The R3A range contains only
the shadow observer, its semantic manifest, fixtures/tests, workflow wiring,
and documentation; legacy writers, DNS/network/firewall dataplane, init,
parser, renderer, installer, package, and version behavior are unchanged.
All local R3A gates passed (typed shadow 14/14, D2B 21/21, R2B 18/18,
canonical config 10/10, runtime shadow 11/11, self-sufficiency 23/23,
`local-gate.sh`, `ci-gate.sh`, validation, POSIX syntax, compileall, and
diff-check). The frozen writer hashes remain unchanged.

The only R3A runtime candidate files are
`luci-app-openkill/root/usr/share/openkill/openkill_nft_shadow.sh` (160557
bytes, SHA-256 `4de3738e953552c7acfa60d39f12c2341341dfd459bf76b46d1491ecd50367ff`)
and `luci-app-openkill/root/usr/share/openkill/shadow/semantic_model_v1.tsv`
(1453 bytes, SHA-256
`7bd6909cfcb08aee02cc6900fee6de358228d7d5b9fef15c634f19c69a4fdb50`). The
shell accepts a temporary manifest through
`OPENKILL_NFT_SHADOW_SEMANTIC_MANIFEST` or `OPENKILL_NFT_SHADOW_TEMPLATE_DIR`
and safely copies caller-provided typed files through
`OPENKILL_NFT_SHADOW_TYPED_ACTUAL_FILE` and
`OPENKILL_NFT_SHADOW_TYPED_DESIRED_FILE`.

The complete device staging path is nevertheless blocked. The production
tree has no sidecar producer: `openkill_shadow_capture_legacy_nft` and
`openkill_shadow_parse_nft_capture` emit legacy capture/intent, and
`openkill_shadow_run_renderer` emits CURRENT nft payload, but no production
caller emits `OPENKILL_SHADOW_TYPED_INTENT_V1=1` actual/desired files from
that same coherent cycle. `openkill_shadow_compare_nft` requires both typed
files and returns `MODEL_GAP` when either is absent. The checked-in typed TSVs
are sanitized local fixtures only; staging them would not be live `.102`
evidence. R3B therefore stopped before SSH or any device write:
`CANDIDATE_STAGING_ENTRYPOINT_BLOCKER`, `R3A_CANDIDATE_REAL_DEVICE=NOT_RUN`,
and `DEVICE_TYPED_*_PARITY=INSUFFICIENT_EVIDENCE`. No device or router was
accessed and no package, service, UCI, dataplane, config, or central write
occurred.

`NEXT=R3B_LOCAL_TYPED_SIDECAR_PRODUCER_INTEGRATION` (local only: add and
validate a formal sidecar producer or an equivalent existing production
caller before another device run). `CENTRAL_ACTIVE=NOT_APPROVED`,
`CENTRAL_NFT_APPLY=NOT_APPROVED`, and `REAL_PACKET_PATH=NOT_TESTED` remain
unchanged.

## Phase 3E.2D2D-R3C — self-contained typed sidecar producer integration

Observed locally on 2026-09-16 from baseline
`f710e572c1e9524feae8f4919b9a93ad64422a38`, version `2026-1128`, with no
device or router access.  The D2C commit remains an ancestor.  The R3C scope
is limited to the production shadow observer, its semantic manifest, sanitized
automatic-state fixture, local producer tests, CI suite wiring, and this
documentation; legacy writers, DNS/network/firewall dataplane behavior,
renderer, parser, init, installer, package, and version behavior are unchanged.

R3B's blocker was reproduced locally: the typed comparator accepted prepared
sidecars, but the automatic coordinator had no producer and returned
`MODEL_GAP` when those files were absent.  R3C adds a self-contained producer
inside the same private coordinator cycle.  After coherent T0/T1 capture and
parser output, the formal inventory and CURRENT renderer run; the coordinator
then emits independent `OPENKILL_SHADOW_TYPED_SIDECAR_V1` actual and desired
files and feeds them directly to the existing typed comparator.  The actual
side uses parsed legacy intent and snapshot-frozen scalar fields.  The desired
side uses CURRENT renderer output for firewall DNS targets plus renderer input,
templates, and explicit manifest contract records for desired objects and the
remaining DNS layers.  No producer step performs a live UCI, ubus, nft, ip,
DNS, or Mihomo reread after the snapshot.  D2A inventory classification runs
before typed projection, so required absence remains fail-closed while
conditional, inactive, optional, and out-of-scope absences remain explicit
diagnostic evidence.

The sidecars carry schema, model, side, cycle, and continuity metadata and are
bounded mode-0600 files in the private temporary directory.  Missing or
ambiguous sources, duplicate rows, or unknown ownership return the additive
`MODEL_GAP` result (exit 12); present semantic differences remain the existing
`MISMATCH` result.  WAN safety rows remain in full observation and are excluded
from CURRENT-owned equality by formal `LEGACY_ONLY_SAFETY` metadata.  The
independent firewall/listener/upstream/Mihomo/loop/scope fields preserve the
D2C `53` versus `7874` distinction.  External sidecars remain available only
for explicit fixture/development calls; automatic production mode rejects
them even when a legacy override variable is supplied.  The device runtime
remains POSIX shell/BusyBox-only.

Local evidence: automatic no-sidecar replay is `MATCH` with
`DNS_PARITY=MATCH`, one stable actual/desired/DNS hash pair, and retained WAN
observation; renderer mutation and actual-state mutation are independently
detected as `MISMATCH`; missing actual or desired DNS sources are `MODEL_GAP`;
the minimal staged observer/manifest simulation is `MATCH`.  The dedicated
producer suite passes 13/13, including automatic rejection of externally
supplied sidecars with and without a legacy override; the explicit typed suite
passes 14/14, self-sufficiency 23/23, continuity 11/11, BusyBox normalization
7/7, runtime shadow 11/11, and context adapter 15/15.  The broader local
matrix passes: NFT IR 16/16, NFT syntax 18/18 (`nft` CLI unavailable, so the
syntax matrix is explicitly not run), device parser 7/7, network 65/65,
snapshot/FW4 6/6, Stage D 7/7, runtime 28/28 with two existing skips,
installer 11/11 with one existing skip, core validation, BusyBox renderer
13/13, and autonomous workflow 8/8.  `local-gate`, `ci-gate`, POSIX syntax,
compileall, and diff-check pass.  `NEW_UNEXPLAINED_SKIP=0`.  No version,
package, release, tag, device, central apply, or packet-path operation is part
of R3C.

`R3B=PARTIAL` remains a historical device gate because the installed release
has not been tested with this candidate.  `R3C=PASS`:
`AUTO_TYPED_PRODUCTION_PATH=READY`, `SELF_CONTAINED_STAGING=READY`,
`LOCAL_R3_REPLAY=MATCH`, and `DEVICE_RETRY_READY=YES`.
`NEXT=PHASE_3E2D2D_R3B_RETRY_SELF_CONTAINED_TYPED_CANDIDATE`.
`CENTRAL_ACTIVE=NOT_APPROVED`, `CENTRAL_NFT_APPLY=NOT_APPROVED`, and
`REAL_PACKET_PATH=NOT_TESTED` remain unchanged.

## Local validation hardening work package (completed)

Observed on 2026-09-16 from `28811e56d04b77963e5e5b8b6254b4dc741b8aac`,
version `2026-1128`, with no device or router access.  The D2C commit
`566fa82f0b814710b290c4bbd7e2385b689bd616` remains an ancestor.  The local
changes are limited to the shadow observer's read-only DNS provenance capture,
staged observer tests, the unified test runner, gate naming, evidence
documentation, and CURRENT status; legacy writers, dataplane behavior, init,
renderer, parser, network, firewall, installer, package, version, release and
central-apply behavior were not changed.

The observer now treats `OPENKILL_DNS_ENDPOINT` as readiness/configuration
intent only.  Automatic actual `MIHOMO_DNS_LISTENER` evidence comes from a
supported-core-owned UDP `netstat` socket, joined to the actual dnsmasq
upstream port when Mihomo has multiple listeners; the returned endpoint is
still taken from the socket row.  DNS sources are frozen at T0 and re-sampled
only at the T1/T2 continuity boundaries, while the producer/comparator never
performs a live reread.  Missing or ambiguous sources remain a typed
`MODEL_GAP`/stale cycle.  The staged regression copies the observer, renderer,
semantic manifest and TUN template into a private directory, verifies the
observer hash through a separate wrapper without modifying candidate bytes,
records all candidate paths/hashes and runs five automatic cycles without
external typed sidecars.  The runner source contains no repository helper,
renderer or template fallback.

The single `scripts/openkill-test-gates.py` executor provides `fast`, `full`,
and `device-preflight` modes.  It selects Windows/WSL per case, captures every
return code, records explicit environment-limited results, binds cache keys to
source/test/fixture/interpreter inputs, and writes machine-readable evidence
bundles.  The candidate manifest's minimal staging set is the observer,
renderer, `shadow/semantic_model_v1.tsv`, and `shadow/input_tun_v1.tsv`; its
candidate ID is
`caaf4a28865dce66150758e4b2dc3ca347bbc5620ae8fefe5984084aafbb7c40` and the
canonical config remains
`scripts/fixtures/3e2-safe.yaml` with SHA-256
`9cd8d91750758823776df9c982c1e15f0baa1a72baa1792fa2f82c0df4d24a6e`.

Evidence is complete for the current worktree: fast run
`20260916T140505Z-2412` passed; full run `20260916T140752Z-19340` passed with
32 PASS and one documented `NOT_RUN_ENVIRONMENT` (`NFT_CLI_UNAVAILABLE`);
device-preflight run `20260916T142142Z-21440` passed with 25 PASS and the same
single environment result.  The staged observer test is 16/16, the R2B UCI
lifecycle test is 18/18, and the candidate manifest reports staged execution,
internal typed sidecars, no repository fallback, `DEVICE_ACCESS=0`,
`CENTRAL_APPLY=0`, and `PACKET_TEST=0`.  The candidate ID is
`caaf4a28865dce66150758e4b2dc3ca347bbc5620ae8fefe5984084aafbb7c40`; its
runner source hash is
`b570de29a31207a3a2cefb3c8a75bfcb07334a254ff1cf4172aab11edc44974a`.
The WSL Ruby-dependent cases declare `RUBY_UNAVAILABLE` explicitly.  The
eight frozen writer hashes are unchanged and `NEW_UNEXPLAINED_SKIP=0`.

This proves local readiness only.  `DEVICE_RETRY_READY=YES` means the exact
candidate may be considered for an explicitly approved `.102` phase; it does
not claim device verification, package release, central apply, or packet-path
validation.  `NEXT=PHASE_3E2D2D_R3B_RETRY_SELF_CONTAINED_TYPED_CANDIDATE`.

## NaiveProxy installer current device recheck (2026-09-23)

- User authorized reconnecting to `192.168.1.103` to diagnose and repair the
  optional component installer. This bounded device phase permits diagnostic
  downloads and the component's own installation only; it does not permit
  changing OpenKill traffic policy, CENTRAL_ACTIVE, firewall ownership, WAN,
  or other nodes/subscriptions.
- Current recheck from SSH: package is `luci-app-openkill 2026-1142` and the
  OpenKill service is running. Three earlier tasks failed at `probing` with
  `loader-or-version-probe-failed` and a kernel `Trace/breakpoint trap` while
  executing `naive.new --version`. The configured official OpenWrt x86_64
  asset was fetched in a private temporary directory; its SHA256 matched, and
  the binary's version and help probes succeeded. The exact installed helper
  then succeeded in both isolated synchronous and worker modes. A fresh run
  through the helper's locked asynchronous install task also succeeded; the
  configured `/etc/openkill/core/naive` is now root-owned, executable, and
  reports `150.0.7871.63`. Refreshed state reports `component_installed=1`,
  `state=disabled`, `reason=no-enabled-nodes`, `local_ready=0`, and
  `remote_verified=0`. The old probe trap was not reproducible; no source
  installer defect was confirmed. No Naive node was enabled and no remote
  authentication or packet-path test ran.
- Navigation root cause: the compatibility template linked to `servers` with
  `add=naiveproxy` but omitted the required selected YAML `file` parameter.
  The `servers` model therefore followed its designed no-file redirect to
  Config Manage, exactly matching the screenshot. The node editor, share-link
  parser, and NaiveProxy CBI type already exist.
- Implementation: the compatibility view now uses the selected, existing
  YAML path from the OpenKill UCI accessor, validates that it is under the
  configuration directory and a YAML file, URL-encodes it, and opens the
  server/group manager with the Naive add hint. With no valid selection it
  links to Config Manage and says a configuration must be selected. Creating
  a proxy from that explicit flow carries the NaiveProxy type hint into the
  editor; existing node types remain authoritative. Related edit links retain
  encoded file paths. Network policies, node credentials, DNS, firewall,
  legacy writers, ABI, and start/restore behavior are unchanged.
- Device backup: `/etc/config/openkill` is preserved outside the repository at
  `D:\openkill-device-backup-20260923-current\openkill.config`; local SHA256
  `0bf7be81c9f5d8b959722978e8ee40c66392a2a5ee3165b2f14ed229a0dca52c`,
  matching the device before component installation. The repeat component
  install did not modify UCI or restart OpenKill; service remains running.
- Local checks: NaiveProxy integration contract, UI contract (25), UI preview
  (2), POSIX shell syntax, `git diff --check`, and `scripts/local-gate.sh`
  pass. Browser automation is unavailable in this session, so no rendered
  screenshot is claimed.
- Source implementation commit `a1e39bf7b7c79f9ec2fe47a6847455e78e82cceb`
  is on master. Its exact Development CI passed
  ([35879368818](https://github.com/dinggood615/openkill/actions/runs/35879368818)).
- RC Build from that commit passed
  ([35879571748](https://github.com/dinggood615/openkill/actions/runs/35879571748)).
  The candidate package is
  `luci-app-openkill_2026-1142_all.ipk`, SHA256
  `4e979f1e3e2c7c5eafdb57713f0b2b3356c1fa9e901d0fb56620187efd5214a5`.
  The archived view and both node-management models match source hashes;
  package ownership is root:root and the workflow audit passed metadata,
  conffile, maintainer-script, stale-reference, and sensitive-content checks.
- Device candidate upload hash matched. `opkg install` correctly treated the
  same-version package as already current; the authorized retry with the
  device-supported `--force-reinstall` installed the candidate. The installed
  compatibility view hash matches the RC/source, and marker checks found the
  path and Naive type hint. Current selected config is
  `openkill.optimized.yaml`. Device `/etc/config/openkill` remains at the
  pre-install SHA256; OpenKill is running and enabled; Naive reports
  `150.0.7871.63`; component state is installed, with no enabled node and no
  local/remote verification. The package manager kept the modified conffile
  and placed its packaged default alongside it as `/etc/config/openkill-opkg`.
  The protected backup remains at
  `D:\openkill-device-backup-20260923-current\openkill.config`.
- No browser surface was available in this session, so a rendered click-through
  was not captured. The deployed view and route inputs were verified over SSH;
  remote Naive authentication and business traffic remain untested.
- Version metadata and release notes for 2026-1143 are now prepared; the
  release bump check, NaiveProxy integration contract, UI contract (25), UI
  preview (2), `git diff --check`, and local gate pass. Next action: commit and
  push this versioned source state, verify exact Development CI, build/audit
  its RC, then invoke Formal Release with both required inputs. Preserve
  v2026-1142 and its package for rollback.

## NaiveProxy node-entry fix: final release and device verification (2026-09-23)

- Final source state: `a6df1575ba3608c8c5503574e6f776abda19fc59` on `master` (implementation is in `a1e39bf7b7c79f9ec2fe47a6847455e78e82cceb`; 2026-1143 release metadata is in the final source commit). The selected-config-aware link now reaches the proxy/group manager and preselects the NaiveProxy node type for a newly added proxy. Missing/invalid selected YAML is handled with an explicit configuration-manager path; existing node types and UCI values are retained.
- Formal Release workflow with `release_gate=true` and `publish=true` completed successfully: [run 35881678974](https://github.com/dinggood615/openkill/actions/runs/35881678974). Release: [v2026-1143-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1143-ipk). Asset `luci-app-openkill_2026-1143_all.ipk`, SHA-256 `d0c6aa5e567f4becf77237ee2fd3261551630b3218c21ce6c0266743e0f229d6`. Previous v2026-1142 release remains available.
- Versioned source commit Development CI passed: [run 35880869413](https://github.com/dinggood615/openkill/actions/runs/35880869413). Versioned RC Build passed: [run 35881071698](https://github.com/dinggood615/openkill/actions/runs/35881071698); RC package SHA-256 `24cb6b3774270db91b0478880669c0caf213ca1c6ed8b708745c7b5bfae4ae03`. Formal artifact audit confirmed package version 2026-1143, architecture `all`, expected dependencies and conffile, changed Lua files matching source, and root ownership/modes.
- Formal package was uploaded to the authorized test router; upload SHA matched the release asset. `opkg` upgraded 2026-1142 to 2026-1143. Fresh SSH recheck confirms package version 2026-1143, `/etc/init.d/openkill status` is `running`, ubus reports the core instance running, and the Naive binary remains executable as root and reports `150.0.7871.63`. Installed compatibility view SHA-256 is `17ba7e33cc45272af393c5887d18d149853a75bcd05e51a827fac41af292519c`, matching the candidate/source view. Existing `/etc/config/openkill` hash remains `0bf7be81c9f5d8b959722978e8ee40c66392a2a5ee3165b2f14ed229a0dca52c`; package-manager default copy `/etc/config/openkill-opkg` is separately backed up at `D:\openkill-device-backup-20260923-current\openkill-opkg`, SHA-256 `7b0f83a2aef735f20137902bb2e7d8cfdbb21b3adeff6b78713acaae5a9ea1d1`. The primary protected backup remains `D:\openkill-device-backup-20260923-current\openkill.config`.
- Installed component and node state are distinct: the component is installed, but there is no enabled Naive node. Therefore no local SOCKS5 listener or remote authentication was tested, and no remote connection is claimed. No browser surface was available for a rendered LuCI click-through; device files, route inputs and live service state were verified over SSH.
- Local evidence remains: NaiveProxy integration behavior contract, UI contract (25), UI preview (2), POSIX shell syntax, `sh scripts/local-gate.sh`, and `git diff --check` all passed before versioned commit. The root cause was the omitted selected-YAML `file` query parameter; no DNS, routing, firewall, subscription, node credential, or startup/restore policy was changed.
- Rollback: reinstall the retained `luci-app-openkill_2026-1142_all.ipk` package from the existing v2026-1142 release and restore the protected `/etc/config/openkill` backup only if the user’s config was changed. The upgrade preserved the current config hash, so config restoration is not needed for this release. Naive component binary was retained across OpenKill package upgrade.
- Documentation-only evidence commit follows the release; it does not advance the version or rebuild/publish another release. Verify its Development CI separately. Next action: wait for any later user-requested scope; no unresolved local code blocker remains for the Naive node-entry route.

## UI compactness and copy pass (2026-09-24)

- Scope: unify OpenKill page spacing, card surfaces, controls, status labels and responsive grids; shorten repeated visible notes and status summaries. DNS, IPv6, TUN, routing, filtering, proxy protocol, UCI field names, legacy writers, ABI and startup/restore contracts are unchanged.
- Cache contract: local generated output stays under `D:\openkill-cache`; repository cache paths remain junctions and no cache, credentials, device logs or private configuration may enter Git.
- Presentation contract: important privacy, interruption, validation and unsupported-protocol limits remain visible. Technical diagnostics stay in expandable/detail paths. “Saved”, “applied”, “loaded” and “verified” remain distinct states.
- Verification contract: run the existing UI contract/preview checks, local gate and diff checks. Browser rendering evidence is recorded only when the browser runtime is available; unavailable device/browser checks remain explicitly unverified.
- Implementation: `flat.css` now applies the compact spacing/radius/description rhythm to status and settings cards; NaiveProxy metadata/status copy and the dashboard ad summary were shortened without changing DOM hooks, UCI fields or state decisions.
- Local evidence: UI contract 25/25, UI preview 2/2, POSIX/local policy gate and `git diff --check` passed at the 2026-1144 working state. The first WSL gate invocation was environment-blocked by Git safe-directory policy; registering `/mnt/d/openkill` for the WSL test user and rerunning passed. No browser surface is available for rendered screenshots in this session.
- Release gate: version metadata is prepared for 2026-1144. Next action is exact Development CI, RC audit, then Formal Release only after those gates pass; preserve v2026-1143 for rollback.
- Versioned source commit `5bf4434eff786fee804f36782e2fc0b3df39f57b` passed exact Development CI ([run 35982382778](https://github.com/dinggood615/openkill/actions/runs/35982382778)). RC Build passed ([run 35982500360](https://github.com/dinggood615/openkill/actions/runs/35982500360)); the audited candidate `luci-app-openkill_2026-1144_all.ipk` has SHA-256 `0b2b3b895bab33c6ce37dea9efaf5c6a7d0e764254c9ec22314769f1a57b88db`. The audit reported package metadata, conffile preservation, maintainer-script deletion, stale-reference and sensitive-content checks as OK. The package was unpacked from the RC artifact and confirmed to contain the compact CSS marker, shortened NaiveProxy copy and corrected ad status wording.
- Formal Release with `release_gate=true` and `publish=true` passed ([run 35983177776](https://github.com/dinggood615/openkill/actions/runs/35983177776)). Published release: [v2026-1144-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1144-ipk), source `5bf4434eff786fee804f36782e2fc0b3df39f57b`, asset `luci-app-openkill_2026-1144_all.ipk`, downloaded SHA-256 `29f29332f785a315c34586eeb72afc38aec8fb13a572775ab890b13d2dc1e9e` (9,225,962 bytes). v2026-1143 remains available for rollback.
- Browser rendering was not claimed because this host has no available browser runtime. No device installation was requested in this UI-only pass; device state and remote business behavior remain unverified. No DNS, routing, filtering, protocol or startup policy was changed.

## Runtime status dashboard alignment and copy pass (2026-09-25)

- Scope: adjust only the runtime status page presentation: five-card copy,
  dashboard DOM grouping, responsive grid sizing and state-summary display.
  DNS, IPv6, TUN, routing, filtering, protocol behavior, UCI fields, status
  endpoint semantics and startup/restore contracts remain unchanged.
- Layout contract: the visual top row is one responsive grid with Running
  Status at roughly 1/2 width and Control Panel/Mix Proxy at roughly 1/4
  each. The lower primary and secondary columns stretch from one shared grid
  row; no filler card, fixed-height spacer, negative margin or whole-page
  scaling is allowed.
- Copy contract: each DNS, adblock, OpenVPN, RustDesk and NaiveProxy card
  keeps one evidence-based primary state plus one short necessary detail.
  Generated, loaded, applied and verified remain distinct; unknown and
  unverified states cannot be presented as healthy.
- Verification contract: exercise the existing preview states (running,
  disabled, startup_failed and error), UI contract/preview tests, local-gate
  and diff checks. Browser rendering is recorded only if a browser runtime is
  available; device and packet-path validation are outside this UI-only scope.
- Next action: implement the scoped status template/CSS changes, run local
  gates, then prepare the next version only after the exact-commit CI and RC
  audit pass.

## Runtime status dashboard alignment release evidence (2026-09-25)

- Implementation commit `8f52fe5c5c0f54b41ed8421ed240773fc9eb29e5` shortens
  the five live summaries while preserving full evidence in accessible detail
  labels, changes the top grid to `2fr 1fr 1fr`, and lets the primary config
  card and secondary metric matrix stretch across one shared lower grid row.
  No network policy, state endpoint semantics, UCI field or startup/restore
  behavior changed.
- Local evidence: UI contract 25/25, UI preview 2/2, POSIX/local policy gate,
  version bump check and `git diff --check` passed. Browser automation is not
  available in this environment, so rendered viewport measurements and
  screenshots remain unverified; device validation was not requested.
- Versioned source commit `fef4244ea88fcf4a0ead6adf90d3f144ca6f0623`
  (`2026-1145`) passed exact Development CI
  ([run 36105228266](https://github.com/dinggood615/openkill/actions/runs/36105228266)).
- RC Build from the same source passed
  ([run 36105449460](https://github.com/dinggood615/openkill/actions/runs/36105449460)).
  Candidate `luci-app-openkill_2026-1145_all.ipk` SHA-256 is
  `79f8c8a128e92a03d144d097292790f29bcd123b097f738f02baf03313ad260e`.
  The workflow audit passed package metadata, conffile preservation,
  maintainer-script deletion, stale-reference and sensitive-content checks;
  the extracted candidate contains the new status template and CSS markers.
- Formal Release with `release_gate=true` and `publish=true` passed
  ([run 36105951841](https://github.com/dinggood615/openkill/actions/runs/36105951841)).
  Published release:
  [v2026-1145-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1145-ipk),
  source `fef4244ea88fcf4a0ead6adf90d3f144ca6f0623`, asset
  `luci-app-openkill_2026-1145_all.ipk`, SHA-256
  `47c5e5e4ac308e6e493e7df86f27f5b8a3db404f774092ff23e47426037c5a68`.
  The formal asset was downloaded into `D:\openkill-cache\formal-2026-1145`
  and its extracted status template/CSS matches the versioned source.
- Previous `v2026-1144-ipk` remains available for rollback. No router,
  central nft state, packet-path test or private configuration was touched.

## NaiveProxy install and bridge handoff (2026-09-25)

- Scope: extend the existing NaiveProxy metadata/install action with a compact
  share-link entry path and a read-only, credential-free YAML preview for the
  generated loopback SOCKS5 bridge. The existing UCI fields, helper process,
  node identity, port allocation, Mihomo writer and failure recovery contract
  remain the source of truth.
- Installation contract: the one-click action must keep the official asset
  URL and expected SHA-256 bound together, use the existing staged background
  task, preserve the previous component on failure, and never start a helper
  when no NaiveProxy node is enabled.
- Node contract: the compact importer delegates parsing to the existing
  structured NaiveProxy URL parser, keeps credentials in protected UCI only,
  and preserves stable server section IDs and policy-group behavior.
- Bridge contract: the preview exposes only name, 127.0.0.1, allocated port,
  and `udp: false`; it must match the actual Mihomo SOCKS5 stanza generated by
  `yml_proxys_set.sh` and must not expose credentials or claim remote success.
- Verification contract: run the NaiveProxy integration, UI contract,
  preview, local-gate and diff checks. Browser, device and remote endpoint
  validation remain explicitly unverified in this local-only change.

## NaiveProxy bridge release evidence (2026-09-25)

- Implementation commit `eca8ff25d753e6bc7743981f8bcaf9b58d328ddf` passed exact
  Development CI ([run 36111656314](https://github.com/dinggood615/openkill/actions/runs/36111656314)).
  It adds the bridge status endpoint, compact share-link importer and a
  credential-free SOCKS5 YAML preview while preserving existing install and
  helper lifecycle contracts.
- Version commit `e1762b9e99451e1ac826e520de9fef2dc21b76e1` (`2026-1146`)
  passed exact Development CI ([run 36111847076](https://github.com/dinggood615/openkill/actions/runs/36111847076)).
- RC Build passed ([run 36111987140](https://github.com/dinggood615/openkill/actions/runs/36111987140)).
  Candidate `luci-app-openkill_2026-1146_all.ipk` SHA-256 is
  `f0b9fd4d33d3cb226a3c84dabab7801d0bd7a3616ea85df11d565b35a3e7f0c6`;
  it is archived under `D:\openkill-cache\rc-2026-1146`. The workflow audit
  passed package metadata, conffile preservation, maintainer-script deletion,
  stale-reference and sensitive-content checks. Extracted files contain the
  bridge endpoint, quick importer and `udp: false` SOCKS5 stanza.
- Formal Release with `release_gate=true` and `publish=true` passed
  ([run 36112629048](https://github.com/dinggood615/openkill/actions/runs/36112629048)).
  Published release: [v2026-1146-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1146-ipk),
  source `e1762b9e99451e1ac826e520de9fef2dc21b76e1`, asset
  `luci-app-openkill_2026-1146_all.ipk`, SHA-256
  `fc5ab070c3b27ac6fac23653b81f405bad2e3484ae93e21194a12556a582ab1f`.
  The formal asset is archived under `D:\openkill-cache\formal-2026-1146` and
  contains the same bridge, importer and UI markers. `v2026-1145-ipk` remains
  available for rollback.
- No device, browser-rendered viewport, remote Naive endpoint or packet-path
  validation was performed in this local-only change. Local integration,
  UI-contract, preview, POSIX/local-gate and package audits passed; credentials
  and private configuration were not touched.

## One-click NaiveProxy installer release evidence (2026-09-25)

- Implementation commit `1967eb87530f5884be3faa2c3cd0ad56e0a0bfd6` adds the
  non-fatal installer phase and installer contract coverage. Its first
  Development CI attempt ([run 36115591993](https://github.com/dinggood615/openkill/actions/runs/36115591993))
  correctly rejected an intermediate commit whose version fields were split
  across commits; no package was published from that state.
- Versioned source commit `30f847b8a08733fda952efb78e5b599c1ef41b5f`
  (`2026-1147`) contains the synchronized Makefile, installer, README, UI
  preview and release notes. Exact Development CI passed ([run 36115735658](https://github.com/dinggood615/openkill/actions/runs/36115735658)).
- Local evidence passed after the repair: installer tests 12/12 (one host
  dependency skip), NaiveProxy integration contract, POSIX syntax checks,
  local-gate and `git diff --check`. The integration test now decodes WSL
  diagnostics with replacement handling so locale noise cannot mask syntax
  results.
- RC Build passed ([run 36115884484](https://github.com/dinggood615/openkill/actions/runs/36115884484)).
  Candidate `luci-app-openkill_2026-1147_all.ipk` SHA-256 is
  `02452a7532b9e4f8540f2903b3e025b6d55c9e2756bcd7606fb25d8087f9026f`;
  it is archived under `D:\openkill-cache\rc-2026-1147`. The audit passed
  package metadata, conffile preservation, maintainer-script deletion,
  stale-reference and sensitive-content checks.
- Formal Release with `release_gate=true` and `publish=true` passed
  ([run 36116332106](https://github.com/dinggood615/openkill/actions/runs/36116332106)).
  Published release: [v2026-1147-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1147-ipk),
  source `30f847b8a08733fda952efb78e5b599c1ef41b5f`, asset
  `luci-app-openkill_2026-1147_all.ipk`, SHA-256
  `d9877d85489e74cd8cfa42d2ac4aed4e91c34f55b9f82ee452cfe6a6514469ea`.
  The formal asset is archived under `D:\openkill-cache\formal-2026-1147`;
  its extracted files include the NaiveProxy metadata helper, component path,
  bridge endpoint and SOCKS5 writer. `v2026-1146-ipk` remains available for
  rollback.
- No router, device, browser-rendered viewport, remote Naive endpoint or
  packet-path validation was performed. The one-click installer still treats
  metadata/download/component failures as non-fatal to OpenKill and does not
  start a helper without an enabled NaiveProxy node.

## One-click NaiveProxy installer handoff (2026-09-25)

- Scope: extend the existing OpenKill installer with an optional, non-fatal
  NaiveProxy component phase. The phase consumes the official metadata
  resolver's bound URL and SHA256 pair, installs only after ELF and version
  checks, and records the pair only when the corresponding UCI fields are
  empty. It never starts a helper or changes transparent proxy ownership.
- Path contract: installer, status probe, service lifecycle and Mihomo writer
  must use the configured `/etc/openkill/core/*` component path. A manually
  installed fallback is diagnostic evidence until it passes the same executable
  and version checks and is explicitly adopted.
- Failure contract: metadata, downloader, digest, archive, architecture and
  loader failures keep OpenKill usable and preserve a previous component;
  installer output identifies the NaiveProxy phase without exposing credentials.
- Bridge contract: enabled nodes still produce protected helper JSON, a stable
  loopback SOCKS5 port, and a matching Mihomo `type: socks5` stanza with
  `udp: false`; automatic YAML injection and user-managed snippets must not
  create duplicate names or imply remote verification.
- Verification contract: add installer contract coverage for metadata success,
  missing metadata, existing component reuse and non-fatal failure; rerun the
  NaiveProxy, UI, POSIX and local-gate suites. Device and remote endpoint tests
  remain outside this local phase.

## 2026-1151 release evidence (2026-09-25)

- Source fix commit: `1e2fcfd179beec3bc21f84f649d8cd5d8d043958`.
- Development CI for the exact commit passed: [run 36139159582](https://github.com/dinggood615/openkill/actions/runs/36139159582).
- RC Build passed from the exact commit: [run 36139343804](https://github.com/dinggood615/openkill/actions/runs/36139343804). The SDK audit summary reported `luci-app-openkill_2026-1151_all.ipk`, SHA256 `9b2280983fb956dfdf5cbc88f18524a8a4280b77bb7f45554746912d388335fb`.
- Formal Release passed with `release_gate` and `publish`: [run 36139865576](https://github.com/dinggood615/openkill/actions/runs/36139865576). Published [v2026-1151-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1151-ipk); formal IPK SHA256 `f63c8ae3f1a57010fc78786b2e1f091b0806e7ae36d7b76dd6372c1494a5b704`.
- Root cause was confirmed on the authorized device: `tblsection.htm` passed an URL-encoded `file=%2F...` route through Lua `string.format`, so `%2F` was parsed as a format directive and the NaiveProxy add/import editor failed before rendering. The fix replaces only the explicit `%s` placeholder and preserves encoded query bytes.
- Device backup before the formal install: `/tmp/openkill-naive-1151-backup-20260925-212115/config.tgz`, SHA256 `4d7e63e516bc6e47ad67dd1d35a0ca91f3f2b06623c035b7ac8b7408e26d784`.
- Device post-install evidence: OpenKill `2026-1151`, service `running`, `/etc/openkill/core/naive` executable, 127.0.0.1:11080 ready, fixed TCP SOCKS probe returned HTTP 204, helper state `configured=1/generated=1/component_installed=1/local_ready=1/remote_verified=0`. No DNS, routing, firewall, or central nft changes were made.
- Browser evidence on the formal package: both “添加 NaiveProxy 节点” and “导入分享链接” opened the existing node editor with the encoded configuration path intact; no Runtime error was rendered. The existing node and protected configuration were preserved.
- Remote Naive authentication, UDP forwarding, IPv6 behavior, and application-level streaming remain unverified because the test only used a fixed local TCP probe.

## NaiveProxy direct node flow and device loop repair (2026-09-25)

- Scope: route the compatibility-card Add/Import actions directly to the existing NaiveProxy node editor by creating a marked, disabled draft section; retain the generic server manager for management and keep the legacy encoded-file route intact. Draft sections are cleaned only when a new direct-add flow begins, so ordinary user nodes are never removed.
- UI contract: the page continues to own one node editor and one UCI source. Add/import must not open the generic server list; import remains a structured preview in the existing editor. The direct endpoint preserves the selected YAML path and the `type=naiveproxy`/`import=1` hints.
- Device contract: before changing the authorized test device, archive OpenKill configuration, component and runtime state. Remove the previously imported private Naive node only after the backup, without touching unrelated nodes, subscriptions or YAML. Keep credentials out of logs and reports.
- Outbound contract: OpenKill's existing fw4/legacy writers reserve GID 65534 as the self-traffic bypass. NaiveProxy helper instances remain root-owned for protected configuration but run with group `nogroup` so their remote TCP sockets are not recursively intercepted. No new central nft state, WAN change or broad port exemption is introduced.
- Verification: test direct routing and draft creation statically and in LuCI; on the device confirm the helper's effective group, bounded file descriptors, local SOCKS5 readiness and a redacted TCP probe. Remote authentication, UDP, IPv6 and streaming remain unverified unless a non-secret endpoint test provides evidence.

## 2026-1152 direct NaiveProxy entry and loop-repair release evidence (2026-09-25)

- Source commits `904fdcfe580547d18f346c7e771a9d40397a2dd1` (direct
  compatibility-card Add/Import route and helper `nogroup` loop fix),
  `6a928ed76eb18c12c6dd02c13ef597ad057d3aca` (version metadata), and
  `352d0b5e63fe637c88e126498c9e6dd503cc66e3` (clear marked draft after the
  editor is submitted) are on `master`. The final exact Development CI passed:
  [run 36143466609](https://github.com/dinggood615/openkill/actions/runs/36143466609).
- Local NaiveProxy integration tests, POSIX/local-gate and diff checks passed.
  The final RC Build from `352d0b5` passed:
  [run 36143804420](https://github.com/dinggood615/openkill/actions/runs/36143804420).
  The formal package is `luci-app-openkill_2026-1152_all.ipk`, SHA-256
  `2a711d3f80b5afc9902f0406500c4aa254f5b9e8a261e697c3a5611bdb006744`,
  archived under `D:\openkill-cache\formal-2026-1152`. The extracted package
  contains the direct `naive_node` route, draft cleanup, `nogroup` helper
  setting, Naive compatibility view and final CSS; archive members retain
  root ownership and expected executable/read-only modes.
- Formal Release with `release_gate=true` and `publish=true` passed:
  [run 36144577215](https://github.com/dinggood615/openkill/actions/runs/36144577215).
  Published [v2026-1152-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1152-ipk)
  from `352d0b5`; the release asset SHA-256 matches the audited package above.
  `v2026-1151-ipk` remains available for rollback.
- Authorized-device backup before cleanup was
  `/tmp/openkill-naive-cleanup-20260925-213824/config.tgz`, SHA-256
  `3822fda3e4be8588acf9f69a373a349b0d131ad0be053a85c6da44ecd47dbb93`.
  The earlier private NaiveProxy node was removed only after this backup; the
  device now has zero NaiveProxy server sections and no private node in the
  source, package or package-default conffile. Existing OpenKill configuration
  and unrelated services were preserved.
- Before cleanup, the device reproduced the failure as repeated helper
  `ERR_INSUFFICIENT_RESOURCES` with approximately 1024 descriptors because the
  root-group helper was recursively intercepted. A temporary `nogroup`
  verification reduced the helper to a bounded descriptor count and a local
  SOCKS5 HTTPS probe returned HTTP 204; this is transport-path evidence only,
  not remote authentication or application access. The formal package now
  carries the same `nogroup` service setting. After formal installation the
  device reports OpenKill `2026-1152`, the core route and direct editor route
  are present, the service core is running, and no Naive helper starts without
  an enabled node. The modified device conffile was preserved by opkg as
  `/etc/config/openkill-opkg`.
- Browser-rendered device UI could not be re-captured in this iteration because
  the browser debugging session detached; an unauthenticated HTTP probe
  correctly returned LuCI 403/login-required. Source/package route checks and
  device installation checks passed. Remote Naive authentication, UDP, IPv6,
  streaming, and full browser viewport validation remain unverified.

## One-click NaiveProxy install failure repair (2026-09-25)

- Reproduction: on the authorized test device, `openkill_naive_metadata.sh cached`
  returned `reason=official-api-unavailable`; `curl` failed the TLS handshake to
  GitHub because Fake-IP DNS resolved `api.github.com` into the synthetic
  `198.18.0.0/15` range. This is a bootstrap metadata-path failure, not proof
  that the selected component asset is invalid.
- UI failure: `autoInstall()` always forced `requestMetadata('detect', true)`.
  When the page already contained a complete URL/SHA256 pair, a metadata API
  failure still prevented the install task from being started. The repair will
  use a complete existing pair directly and only perform metadata discovery
  when either field is missing; incomplete pairs remain blocked.
- Contract: URL and SHA256 remain one bound trusted asset pair; no credentials,
  node data or network-policy changes are introduced. Metadata errors remain
  visible and never silently trigger DIRECT or an unverified download.
- Verification: add behavior coverage that a complete pair starts
  `install-task` without a metadata request, while missing/incomplete pairs
  require successful metadata discovery. Re-run NaiveProxy integration,
  POSIX/BusyBox syntax, local-gate and diff checks, then perform a device
  metadata/install-path regression without restoring private node data.

## One-click installer bounded database refresh (2026-09-25)

- Device reproduction after the 2026-1153 candidate install: the one-click
  installer remained in `/tmp/openkill-installer.*` while sequentially trying
  the four GeoSite/GeoIP/ASN mirrors. The current device resolves public
  GitHub/jsDelivr names to Fake-IP addresses and the TLS attempts fail, so
  each optional database download waits for its full 180-second timeout. The
  packaged databases are already a valid fallback; this delay makes the
  installer appear hung even though the OpenKill package and component steps
  have completed.
- Planned repair: bound the optional database refresh with a single global
  deadline, stop trying further mirrors when the deadline is exhausted, retain
  packaged files, and report the skipped refresh as a non-fatal warning. This
  does not alter DNS, routing, firewall, proxy or NaiveProxy node behavior.
- Verification must cover a fast successful mirror, timeout/synthetic-IP
  failure, deadline exhaustion and preservation of packaged databases. The
  device test will terminate only the stale installer process from this
  reproduction after recording its failure stage; no user configuration or
  node data will be changed.

## 2026-1154 one-click installer release evidence (2026-09-25)

- Source commit `ae0c24bfd17401a8de0a3c3b783c3125f65a7046` is on `master`.
  The exact Development CI passed: [run 36151093802](https://github.com/dinggood615/openkill/actions/runs/36151093802).
- The RC Build passed from that exact source: [run 36151287232](https://github.com/dinggood615/openkill/actions/runs/36151287232).
  Its SDK audit artifact is `OpenKill-openwrt-sdk-audit`, SHA256
  `a0cdb968092d4a49cf64ccc6a610b4d846aeb2e222a33aa4a475333f1fde9f39`;
  the contained `luci-app-openkill_2026-1154_all.ipk` SHA256 is
  `a630e71013f54bc36760c8034161776a5ba411205d757eff26722fb9095991a8`.
  Package metadata, conffile preservation, maintainer-script deletion audit,
  stale-development-reference audit and sensitive-content audit passed.
- Formal Release with `release_gate=true` and `publish=true` passed:
  [run 36152194588](https://github.com/dinggood615/openkill/actions/runs/36152194588).
  Published [v2026-1154-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1154-ipk)
  from the exact source; the formal IPK SHA256 is
  `ec548ab07da4c7d995a3aed7752e9508ee2635ec08e31e44e8c0dda5a5adadaf`.
  `v2026-1153-ipk` remains available for rollback.
- Authorized-device backup before the formal installation:
  `/tmp/openkill-1154-formal-20260925-231502/config.tgz`, SHA256
  `5dcb4773d84d45f55c2363f4e80828e81adab8ac614ddb3d7f132e683fc645ad`.
  The formal package installed as OpenKill `2026-1154`; `/etc/openkill/core/naive`
  is executable and the helper reports `component_installed=1`,
  `configured=0`, `generated=0`, `local_ready=0`, `remote_verified=0`,
  `state=disabled`, `reason=no-enabled-nodes`. No credentials or node data
  were emitted or changed by this verification.
- The stale pre-fix installer process was stopped after its failure stage was
  recorded. The device's selected YAML was absent after that interrupted run,
  so `/etc/init.d/openkill` correctly remains inactive instead of inventing a
  configuration. This is a missing device configuration prerequisite, not a
  claim that a NaiveProxy remote connection was restored.
- Local installer behavior, the global optional-database deadline, service
  state restoration, NaiveProxy integration, POSIX syntax and local-gate all
  passed. The device still cannot reach public GitHub/jsDelivr through its
  current Fake-IP/TLS bootstrap path; component download and remote Naive
  authentication remain device-pending.

## 2026-1160 standalone NaiveProxy bridge release evidence (2026-09-26)

- The standalone migration is implemented in source commit
  `d7aacef60ed4a1a4912cda3b2f164ebd65650ed0`; version metadata and release
  notes were finalized in `6cf5cec505133785cb46da62b48044c716ef68b6` on
  `master`. OpenKill no longer owns NaiveProxy credentials, starts or stops
  the bridge, probes nodes, or injects Naive nodes into Mihomo. The bridge
  owns `/etc/naiveproxy`, `/var/run/naiveproxy`, per-node protected JSON,
  loopback listeners, health state and the `naiveproxy-bridge` procd service.
- Local verification passed: standalone fixture, integration contracts, UI
  contracts and interactions, Python compilation, POSIX syntax, YAML and
  credential-redaction checks, `sh scripts/local-gate.sh`, and
  `git diff --check`. `scripts/test-installer.py` could not run on the Windows
  host because the optional `yaml` module is absent; browser, device and
  real-VPS packet/remote authentication tests remain unverified by plan.
- Exact Development CI passed for the implementation commit:
  [run 36237005619](https://github.com/dinggood615/openkill/actions/runs/36237005619),
  and for the release-preparation commit:
  [run 36237152719](https://github.com/dinggood615/openkill/actions/runs/36237152719).
- RC Build passed from the exact release-preparation commit:
  [run 36237326633](https://github.com/dinggood615/openkill/actions/runs/36237326633).
  The RC IPK is 7,695,999 bytes with SHA256
  `722e1483442a896f932a7430a326012be6099f57d57f890990ae7ed02085e013`.
- Formal Release passed with `release_gate=true` and `publish=true`:
  [run 36237633490](https://github.com/dinggood615/openkill/actions/runs/36237633490).
  It published [v2026-1160-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1160-ipk)
  from commit `6cf5cec505133785cb46da62b48044c716ef68b6`.
  The formal `luci-app-openkill_2026-1160_all.ipk` SHA256 is
  `3cb809939e5f1eb1c47213be0099dc2fdbe635dbbe9b087c25a4f68df1821a4e`.
- Rollback remains `v2026-1159-ipk`; preserve `/etc/naiveproxy` before
  changing packages, stop the independent bridge if needed, reinstall the
  previous IPK, and leave user-managed YAML untouched.

## 2026-1164 Naive import diagnostics and compatibility layout evidence (2026-09-26)

- The follow-up implementation is in `57dd6facdd49c59f2c558990124c35fd443ae338`.
  It decodes percent-encoded Naive share-link fields on the standalone
  parser, reports the component probe reason instead of treating a registered
  path as an available binary, and maps the ZeroTier fields into the
  compatibility remote-access card while keeping system maintenance in the
  adjacent capability grid. The exact Development CI passed:
  [run 36250767369](https://github.com/dinggood615/openkill/actions/runs/36250767369).
- Version metadata and release notes were prepared in
  `d861a9e9f4f8b4ec1f4626e336387b9d7ae371a8`; its exact Development CI passed:
  [run 36250902189](https://github.com/dinggood615/openkill/actions/runs/36250902189).
- RC Build passed from that exact source:
  [run 36251022781](https://github.com/dinggood615/openkill/actions/runs/36251022781).
  The audited RC IPK SHA256 is
  `bd8d02de53d8bf04f50affcc9e53c98a7a1731be601de9045ecae2f6dda2685b`.
  Metadata, conffile preservation, persistent-delete, stale-reference and
  sensitive-content audits passed.
- Formal Release passed with `release_gate=true` and `publish=true`:
  [run 36251278871](https://github.com/dinggood615/openkill/actions/runs/36251278871).
  It published [v2026-1164-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1164-ipk)
  from the exact source above. The formal
  `luci-app-openkill_2026-1164_all.ipk` SHA256 is
  `4a9197c6f2a9aeb43857e970a1d5d8e4e4b9445614c8e8888eb7794168c331ee`.
- Local import, standalone parser, integration and UI contracts, POSIX
  checks, `scripts/local-gate.sh` and `git diff --check` passed. Browser
  rendering was unavailable because Playwright is not installed in this
  environment; device and VPS/remote authentication were not run under the
  current plan and remain unverified.

## 2026-1164 ZeroTier card placement correction (2026-09-27)

- Follow-up layout correction keeps ZeroTier in the compatibility tab as its
  own card. The compatibility grid order is now VPN access policy and remote
  access on the first row, followed by OpenVPN on the left and ZeroTier on the
  right; NaiveProxy remains its own subsequent card. ZeroTier fields are no
  longer grouped inside the remote-access card, and their UCI category and
  behavior are unchanged.
- Local UI and NaiveProxy integration contracts pass after the correction;
  browser rendering remains unavailable in this environment and no device or
  VPS verification was performed.
- The correction commit `5ce2a9a0950cce4250cff928d09c8530b389d567` was pushed
  to `master`; its exact Development CI passed:
  [run 36280949804](https://github.com/dinggood615/openkill/actions/runs/36280949804).

## 2026-1165 maintenance and Mihomo card order (2026-09-27)

- Requested scope: in the system-maintenance tab, place the `系统维护` card
  before and beside `Mihomo 能力` in the same two-column grid. This is a
  presentation-only ordering change; fields, defaults, save behavior and
  capability checks remain unchanged. Desktop rows stretch naturally and the
  existing single-column mobile fallback remains in effect.

- Source `3a8ac4e28e78d3d94cd7d0ca166407045b7e6e5b` passed exact Development
  CI: [run 36281567007](https://github.com/dinggood615/openkill/actions/runs/36281567007).
- RC Build passed from that source:
  [run 36281650248](https://github.com/dinggood615/openkill/actions/runs/36281650248).
  The audited RC IPK SHA256 is
  `6cba456230e6e5be66a9abc06891ce9ba135edcc837c8131900da40c01445e37`;
  package metadata, conffile preservation, maintainer deletion, stale
  references and sensitive-content audits passed.
- Formal Release passed with `release_gate=true` and `publish=true`:
  [run 36281908283](https://github.com/dinggood615/openkill/actions/runs/36281908283).
  It published [v2026-1165-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1165-ipk)
  from the exact source above. The formal IPK SHA256 is
  `7b0ec00012f0ebe4cc736a007b91e2e83b74e7324d7c2e71d9a82d8e6db8b87c`.
- Browser rendering, device verification and real Mihomo/NaiveProxy network
  tests remain outside this local-only iteration; no device state or private
  configuration was accessed.

## 2026-1166 maintenance card full-width regression (2026-09-27)

- Root cause: `createCard()` added the `openkill-settings-card-version-update`
  class to the maintenance card after the card-order change. The shared CSS
  mapped that class to `grid-column: 1 / -1`, so the maintenance card consumed
  the entire row and pushed Mihomo capabilities below it. The fix removes the
  special class and its full-width CSS rule; the maintenance card now follows
  the advanced layout order and participates in the same equal-width grid.
- Scope is presentation-only. Maintenance controls, capability fields, CBI
  IDs, defaults, persistence and mobile single-column fallback remain
  unchanged.
- The first 2026-1166 Development CI exposed a stale installer contract test
  that still required the removed full-width marker; the implementation was
  correct but the test was not updated. The test contract is being repaired
  before RC and Formal Release are retried.

## 2026-1167 maintenance editor layout (2026-09-27)

- Follow-up scope: within the maintenance card only, make the custom firewall
  editor use the full card width and place its description below the editor.
  The global CBI label/field/description layout and all other settings cards
  remain unchanged.

- Source `7543ffbce5bea9751cb7dcc0e459960a2c4d7e4a` passed exact Development
  CI: [run 36283422605](https://github.com/dinggood615/openkill/actions/runs/36283422605).
- RC Build passed from that source:
  [run 36283477998](https://github.com/dinggood615/openkill/actions/runs/36283477998).
  The audited RC IPK SHA256 is
  `18b2a520ad2e34135376a208385b8db0993799be53331a806cfb650c5696261d`.
- Formal Release passed with `release_gate=true` and `publish=true`:
  [run 36283660794](https://github.com/dinggood615/openkill/actions/runs/36283660794).
  It published [v2026-1167-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1167-ipk)
  from the exact source above. The formal IPK SHA256 is
  `f5cb0ceb01c3ab505469dcefb3066e4521fd1f65f0ca845ed5969dccb433473b`.
- `test-installer.py` is not runnable on this Windows host because the local
  Python environment lacks the optional `yaml` module; the exact CI passed
  after its dependency installation. Browser, device and VPS verification
  remain unperformed.

- The repaired source commit `d433d5e3f44a2473fa6f5355a72b9a47d0d5ef29`
  passed exact Development CI:
  [run 36282586838](https://github.com/dinggood615/openkill/actions/runs/36282586838).
  The earlier failed run was not released.
- RC Build passed from the repaired source:
  [run 36282638400](https://github.com/dinggood615/openkill/actions/runs/36282638400).
  The audited RC IPK SHA256 is
  `b3d2198ac37628b069ce746e6f8c3a2742aa8674b608bd3080add7e02e286c49`.
- Formal Release passed with `release_gate=true` and `publish=true`:
  [run 36282866935](https://github.com/dinggood615/openkill/actions/runs/36282866935).
  It published [v2026-1166-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1166-ipk)
  from the repaired source. The formal IPK SHA256 is
  `d97b19aa6fbaf661624139037e88c4fd5dad8ff11116cb4d0b7c5a5a95054af0`.

## Formal release preparation 2026-1169 (2026-09-27)

- The published IPK channel is `v2026-1168`; the release workflow requires a
  strictly newer aligned source version. This release-preparation change bumps
  the synchronized source metadata exactly once to `2026-1169` and adds the
  reviewed version-specific release notes. It does not change runtime or
  network semantics.
- Release scope is the already reviewed repository cleanup and UI/CSS audit
  recorded above. User configuration, compatibility endpoints, OpenKill
  settings and private data remain preserved; no device, WAN, CENTRAL_ACTIVE,
  central nft or packet-path operation is authorized here.
- Required gates, in order: local gate and diff review, exact-source
  Development CI, manual RC Build and candidate audit, then Formal Release
  with `release_gate=true` and `publish=true`. The previous `v2026-1168-ipk`
  assets remain the rollback target until the new release is verified.

### Release attempt 194 repair

- Formal Release run `36296020962` correctly stopped before publication. The
  IPK compile step exposed a malformed section-divider comment in `oc.css`
  (`4568:12`), which the local text checks had not parsed with the release
  CSS minifier. The fix restores the intended multi-line comment only; no
  selector, layout, or runtime behavior changes.
- After the repair, the full local UI/workflow/POSIX/i18n checks and
  `scripts/local-gate.sh` passed again. The same `2026-1169` source version is
  retained; it will use a new exact source commit for Development CI, RC and
  the retried Formal Release. Run 194 produced no release tag or package
  publication.

### Release attempt 195 repair

- Formal Release run `36296478943` reached the compile job but stopped in
  `Update Third-Party Resources` because the five external refresh requests
  returned HTTP 403. The source package already carries checked-in resource
  copies. The bounded workflow repair now attempts the official refresh first,
  explicitly retains a checked-in copy when the source is temporarily
  unavailable, and fails if neither source exists. It does not bypass package
  audits or alter runtime/network semantics.

### Formal release 2026-1169 completed

- Exact source commit `8350ddd841b4c39941726feaadf7e4b155f4aea0` passed
  Development CI [run 36296759854](https://github.com/dinggood615/openkill/actions/runs/36296759854).
- RC Build [run 36296840515](https://github.com/dinggood615/openkill/actions/runs/36296840515)
  passed from that commit. Its audited candidate was
  `luci-app-openkill_2026-1169_all.ipk`, SHA256
  `de0aadd0b38557a1e8da2a21c3619be26629eb62394be4971f0fbee9b90619b8`.
- Formal Release [run 36296926087](https://github.com/dinggood615/openkill/actions/runs/36296926087)
  passed with `release_gate=true` and `publish=true`. It published
  [v2026-1169-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1169-ipk)
  from the exact source commit. The formal IPK SHA256 is
  `ade64ad3483549cadb5ea4813c28db6010f474ea409874c48f1f79f86f6d491c`.
- The formal package retained the previous `v2026-1168-ipk` release as the
  rollback target. No router, test-device, VPS, WAN, CENTRAL_ACTIVE, central
  nft or packet-path validation was performed.

## Formal release 2026-1170 completed (2026-09-27)

- The synchronized source version is `2026-1170`. The scoped implementation
  commit `173d24ffa1625f359eeb3a48807ffc89dfa1bf49` passed Development CI
  [run 36300769551](https://github.com/dinggood615/openkill/actions/runs/36300769551);
  the release-preparation commit
  `24f3064bf9d51691ab5f2813ff7288818d561aec` passed the exact-source
  Development CI [run 36300909417](https://github.com/dinggood615/openkill/actions/runs/36300909417).
- RC Build [run 36301179952](https://github.com/dinggood615/openkill/actions/runs/36301179952)
  passed from `24f3064bf9d51691ab5f2813ff7288818d561aec`. The candidate
  audit produced `luci-app-openkill_2026-1170_all.ipk` with SHA256
  `042b233dccfbb85d0f6fbb5041d5424269f1cc882a54d49b2082b74923c66d68`.
  The uploaded audit artifact digest is
  `sha256:1ec58b5ef57c906c506ebc4b0d7626fe96898fb2a679addfea1a8a7767710340`.
- Formal Release [run 36301308811](https://github.com/dinggood615/openkill/actions/runs/36301308811)
  passed with `release_gate=true` and `publish=true` from the exact source
  commit. It published
  [v2026-1170-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1170-ipk).
  The formal release asset `luci-app-openkill_2026-1170_all.ipk` has SHA256
  `c505ac3459f755f9238660f875e169e87f67651188a6be48a843aa05d7df247a`
  and remains alongside all previous release assets.
- The formal package audit confirmed version `2026-1170`, architecture
  `all`, `/etc/config/openkill` conffile preservation, no destructive
  persistent-path removal, no stale development references, and the scoped
  OpenKill CSS plus official NaiveProxy metadata/installer files. The release
  workflow's runtime and compatibility matrix completed successfully.
- UI evidence remains local/browser only: production-template Chrome checks
  covered 1920/1366/768/390 CSS px with no horizontal overflow and distinct
  light/dark computed surfaces. Installer, NaiveProxy integration/standalone,
  health, import, UI contract/interaction and POSIX/BusyBox fixtures passed;
  Windows direct installer tests still require the repository WSL Python
  environment for PyYAML. No device write, package installation, real VPS
  probe or packet-path test was performed; those remain device/VPS pending.
- Rollback is the existing `v2026-1169-ipk` release (or the prior package
  channel) followed by restoring the previous OpenKill package. The new
  catalog and installer changes do not modify user YAML, subscriptions or
  NaiveProxy node credentials.
- The post-release evidence-only commit `fc5f2877ae1df50af6aec34bec6c80591dc012cf`
  was pushed without a version change and passed Development CI
  [run 36301560954](https://github.com/dinggood615/openkill/actions/runs/36301560954).

## 2026-1170 follow-up: BusyBox byte-reader compatibility (2026-09-27)

- The user supplied a fresh one-click installation log from the test target.
  OpenKill `2026-1170` and Mihomo installed, but the independent component
  stage stopped before metadata/download with `preflight failed
  (missing-od)`. This is a tool-capability failure in the installer: the
  target's BusyBox build does not expose an `od` command name. It is not
  evidence that the official NaiveProxy asset, digest, or node credentials
  are invalid. The captured log contained no node credentials and is not
  copied into the repository.
- The bounded repair will keep ELF/archive verification mandatory while using
  an `od`/`hexdump`/BusyBox-app-let byte reader selected at runtime. If no
  byte reader exists, installation must fail with the named
  `missing-byte-reader` stage. No architecture or digest check may be skipped.
  The standalone library's URL encoding, ELF magic and architecture checks
  must use the same fallback helper.
- Scope is installer and standalone-component compatibility plus isolated
  tests and documentation. No device write, service start/stop, UCI/YAML
  change, CENTRAL_ACTIVE, central nft, WAN/DNS change or VPS probe is
  authorized by this follow-up. After the local fix and exact-commit CI pass,
  the test target may retry the public installer separately under an explicit
  device phase.
- Local follow-up evidence: `test-naiveproxy-standalone.py`,
  `test-naiveproxy-integration.py`, `test-installer.py`, POSIX syntax checks,
  `git diff --check` and `sh scripts/local-gate.sh` pass. An isolated install
  fixture with `od` absent and only `hexdump` available completed the verified
  archive, ELF and architecture path successfully (`NAIVE_NO_OD_FALLBACK=PASS`).
- The bounded fix commit `26249e3d8b7efd4e8c7b8679b2ee99518febe2a8` passed
  the exact Development CI [run 36302301830](https://github.com/dinggood615/openkill/actions/runs/36302301830).
  Because the published `v2026-1170-ipk` contains the preflight that rejects
  this BusyBox target, the next release will advance the synchronized source
  version once to `2026-1171`, retain `v2026-1170-ipk` as rollback, and use
  the normal RC then Formal Release gates. This version change does not grant
  device write or VPS testing permission.

## Formal release 2026-1171 completed (2026-09-27)

- The release-preparation commit `6b14d01cefac183fd9943fe65c442757a8689391`
  passed the exact-source Development CI [run 36302424538](https://github.com/dinggood615/openkill/actions/runs/36302424538).
- RC Build [run 36302499502](https://github.com/dinggood615/openkill/actions/runs/36302499502)
  passed from that commit. The candidate audit produced
  `luci-app-openkill_2026-1171_all.ipk` with SHA256
  `6e4277258da079393150380eb60919c03936218d55288e618749ad3cc0c6cd83`.
  The uploaded RC audit artifact digest is
  `sha256:4d36a075eaedbb64b7cbce964473c44d6ca9d3dbe02ee64f98c60f27e14cf03b`.
- Formal Release [run 36302668502](https://github.com/dinggood615/openkill/actions/runs/36302668502)
  passed all version, compatibility, build and package-audit jobs with
  `release_gate=true` and `publish=true` from the exact source commit. It
  published [v2026-1171-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1171-ipk).
  The formal asset `luci-app-openkill_2026-1171_all.ipk` has SHA256
  `31f6d30e9eb7bb860872bf9be86efc824b1637224ca904937ba26b5e50f7c057`.
- The formal package contains the BusyBox-compatible byte-reader fallback in
  the installer and standalone component library. The audit retained the
  `/etc/config/openkill` conffile, found no destructive persistent-path
  deletion, stale development references or test-machine content, and kept
  the independent component's security checks mandatory.
- Local evidence remains green: standalone, health, integration, installer,
  import, POSIX/BusyBox syntax, no-`od` isolated installation, local gate and
  diff checks. No device write, package installation, real VPS probe or
  packet-path test was performed; the supplied target must retry the public
  installer before device and remote connectivity can be reported.
- Rollback is `v2026-1170-ipk`, followed by restoring the prior OpenKill IPK
  and preserving the user's existing configuration. The fix does not modify
  user YAML, subscriptions, DNS, routing policy or NaiveProxy credentials.

- This release evidence was recorded in commit `3396c17de87c7429a9d4dbe47fe32254b8d1f3a8`;
  its exact-source Development CI [run 36302923885](https://github.com/dinggood615/openkill/actions/runs/36302923885)
  completed successfully. No version metadata was changed by that evidence
  commit.

## Naive import, startup diagnostics and status-card UI follow-up (2026-09-27)

- Baseline is clean `master` at `a8e4af1c2d9c8c0c26ca21863176cadd22954e74`,
  version `2026-1171`. The repository's local standalone, health, integration,
  import, installer and POSIX/BusyBox fixtures pass, but they do not prove a
  live LuCI request or a real official binary on the test target.
- The active plan still forbids device access and writes. No SSH session,
  service start, package install, UCI/YAML change, CENTRAL_ACTIVE, central nft,
  WAN/DNS change or packet-path test is permitted in this follow-up. Device
  diagnosis and real Naive/VPS connectivity remain explicitly pending.
- Baseline review found the browser importer normalizes `naive+https` to a
  generic HTTPS URL and uses client-side query matching, while the service
  parser uses substring checks. The save-and-start path also starts the whole
  bridge instead of binding the requested node, and the status card collapses
  missing, non-executable, loader and version failures into one message.
- This follow-up will keep the independent-service boundary and credential
  protection, add a shared structured import contract with stable field
  persistence, bind save-and-start to the requested node, expose redacted
  component/startup evidence, and simplify dashboard cards to project name plus
  one truthful status. UI changes remain scoped to OpenKill and retain CBI/UCI,
  API, validation and save/apply semantics.
- Required local evidence is the importer behavior suite (including encoded
  credentials, IPv6 and query rejection), standalone persistence and startup
  state fixtures, UI contract checks, final CSS checks, `sh scripts/local-gate.sh`
  and `git diff --check`. Browser rendering and test-device/VPS results must be
  recorded separately; no screenshot or fixture may be called device evidence.

## Follow-up implementation evidence (2026-09-27)

- The independent importer now rejects control characters, malformed percent
  escapes, unknown or duplicate query keys, and unsupported values on both the
  browser and service sides. Supported compatibility hints are validated as
  exact pairs; the saved node JSON remains the source of truth and keeps the
  decoded name, host, remote port, credentials, transport, enabled flag,
  stable ID and stable local port.
- The bridge health path now preserves the actual component probe reason
  (`component-missing`, `component-not-executable` or
  `loader-or-version-probe-failed`) instead of reporting every failure as
  non-executable. The init service exposes node-scoped `start_node` and
  `stop_node` actions; global start/stop behavior remains available.
- The read-only LuCI adapter no longer converts missing numeric evidence to
  zero. The dashboard status card keeps the project name and one live status
  in its default view; longer details remain available through the status
  title/accessible label. The change is scoped to OpenKill and uses the
  existing light/dark variables and content-sized grid.
- Local behavior evidence passed: `scripts/test-naiveproxy-standalone.py`
  (including field persistence, duplicate/unknown/malformed-link rejection),
  `scripts/test-naiveproxy-integration.py`, `scripts/test-naiveproxy-import.js`,
  `scripts/test-installer.py` (15 tests, 1 environment skip), UI contract (29),
  UI preview (2), POSIX syntax, `git diff --check`, and
  `sh scripts/local-gate.sh`. The UI interaction test ran with its documented
  Node/Playwright skip because the local browser dependency was unavailable.
- No live LuCI rendering, test-device write, official binary installation,
  process/PID/listener check or VPS probe was performed in this iteration;
  those remain `设备待验证／远端待验证`. The local fixture does not prove a
  component is installed or a node is remotely reachable.
- The save-and-start request now receives only a redacted stable node ID from
  the independent service's protected runtime result and invokes the
  node-scoped procd action; it no longer needs to start every configured node.
- Source implementation commit `b13b65987afda8ebc81c652a53598f712b7f3d3e`
  was pushed to `master`. Its exact OpenKill Development CI [run
  36306119634](https://github.com/dinggood615/openkill/actions/runs/36306119634)
  completed successfully (static and runtime/compatibility jobs). A final
  documentation-only evidence commit will record this result without changing
  the 2026-1171 version.

## Playwright dependency follow-up (2026-09-27)

- The previously skipped local browser case was caused by the host/WSL test
  environments, not by an OpenKill page failure. Windows had no Node
  `playwright` module at the time of the original probe; WSL had neither the
  Python package nor a browser runtime. After installing developer-only
  dependencies under `D:\\openkill-cache`, the WSL browser initially exited
  with `libnspr4.so` missing. The required WSL shared libraries were then
  provisioned in the same cache and loaded only for the test shell; no OpenKill
  package or production filesystem was changed.
- The real production-template browser run now passes in both environments.
  Windows `scripts/test-ui-browser.py` reports `UI_BROWSER=PASS`,
  `UI_PRODUCTION_JS=PASS`, `UI_DIMENSIONS=4/4` and `UI_LOCAL_REQUESTS=PASS`.
  WSL reports the same result with the isolated Playwright package,
  Chromium 153.0.8010.12 (Playwright v1.63.0) and the cache-only library
  path. The test covered the production template, light/dark surfaces,
  1920/1366/768/390 CSS-pixel viewports, request races, keyboard controls and
  local-request blocking.
- The Node-based interaction harness passes with the Windows Node 24.19.0
  runtime. WSL cannot execute that Windows binary against a WSL temporary path,
  so the WSL Node case remains a separate environment limitation; it does not
  affect the real-browser result. This path mismatch is documented rather than
  changing production JavaScript or introducing a Node runtime into the IPK.
- The fast matrix's UI cases are green after the bootstrap. Two unrelated
  pre-existing host checks remain outside this UI follow-up: the Windows
  canonical fixture requires PyYAML, and the production-shadow suite reports
  its existing OpenVPN command/fixture drift. The bounded local gate,
  UI/browser suites, NaiveProxy fixtures, POSIX checks and diff checks remain
  the release evidence for this change; no device, package-install, WAN/DNS,
  packet-path or VPS test was performed.

## Release preparation 2026-1172 (2026-09-27)

- The synchronized source version is now `2026-1172` in the package Makefile,
  installer and README, with release notes at
  `docs/release/notes/2026-1172.md`. The previous `v2026-1171-ipk` remains the
  rollback target.
- The version-bump check passes against the published `2026-1171` channel.
  WSL installer tests (15 tests, one documented environment skip), UI/browser
  tests, `sh scripts/local-gate.sh` and `git diff --check` pass for the release
  candidate source.
- Exact source Development CI for `7d2e15a66c94940f002c83f2b07e5db7a88d687e`:
  [36307946320](https://github.com/dinggood615/openkill/actions/runs/36307946320)
  completed successfully. RC Build run
  [36308171668](https://github.com/dinggood615/openkill/actions/runs/36308171668)
  completed successfully; its SDK audit artifact digest is
  `sha256:82509e832fae3ad71bf0546f122dc100505a7aad957dce704134dded83147a7f`
  and the candidate IPK SHA256 is
  `6352ba7fd14f6653741c86fa67faa304beb173a2d01233b6b8c5833135b5bb66`.
- Formal Release run
  [36308331238](https://github.com/dinggood615/openkill/actions/runs/36308331238)
  completed successfully with `release_gate=true` and `publish=true`. The
  published package is
  [v2026-1172-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1172-ipk),
  asset `luci-app-openkill_2026-1172_all.ipk`, SHA256
  `62340d7a1ef39b1a252d3df8aeac83b30dcf086769dcb63415ae973ad1515084`.
  The package branch records `v2026-1172`; `v2026-1171-ipk` remains the
  rollback target. No device, package-install, WAN/DNS, packet-path or VPS
  test was performed.

## UI and Naive import follow-up (2026-09-27)

- The import dialog symptom was traced to an unconditional `response.json()`:
  when a LuCI controller exception or expired session returned an HTML
  document, the browser surfaced `Unexpected token '<'` instead of a stage.
  The controller now keeps this boundary JSON-only, catches bridge dispatch
  failures, and has a protected one-shot request-file fallback when the
  embedded Lua runtime has no `io.popen`. The request file is mode 600 and is
  removed after the call; credentials are never command arguments or response
  fields.
- The dialog sends an explicit JSON request preference and maps non-JSON
  responses to `controller-html-response` with a refresh/retry hint. Successful
  imports still pass the share link to the independent bridge, which remains
  the source of truth for decoded fields, stable ID and port; OpenKill UCI and
  user YAML remain unchanged.
- The fallback creates only the fixed mode-0700 runtime directory when the
  platform exposes `nixio.fs.mkdir`, removes any stale control result before
  dispatch, and keeps the one-shot request mode 600. The status dashboard now
  changes an unresolved first poll to truthful `未知` after 12 seconds rather
  than leaving every card on an endless loading label; a later valid poll
  still restores live values.
- The light-theme symptom was caused by legacy `--bg-gray`, `--ok-surface`
  and `--oc-surface` aliases plus `#tab-header` retaining older dark fallback
  values after semantic theme tokens were defined. A page-scoped terminal hand-
  off in `flat.css` maps those aliases to LuCI-derived OpenKill tokens and
  covers Naive dialogs, status navigation and settings controls in both light
  and dark markers. No network or form semantics changed.
- Local evidence: `scripts/test-naiveproxy-integration.py`,
  `node scripts/test-naiveproxy-import.js`, `scripts/test-ui-preview.py`,
  `scripts/test-ui-browser.py`, `scripts/test-ui-interactions.py`, WSL
  `python3 scripts/test-naiveproxy-standalone.py`, POSIX syntax checks,
  `wsl.exe sh scripts/local-gate.sh` and `git diff --check` pass. The native
  Windows standalone fixture was not used as release evidence because its Git
  Bash child process does not terminate in this host; the same fixture passes
  under WSL. Browser evidence is local/mock-backend only.
- No live LuCI device, package installation, official binary probe, process or
  listener check, node credential import, or VPS test was performed. Device and
  remote connectivity remain `设备待验证／远端待验证` under the active plan.
- Development commit `38749047b74dbc1454d761d0da5d0acc8c198487` was pushed to
  `master`; exact-commit Development CI run `36310410689` completed
  successfully. No RC or Formal Release was run for this UI/import-only fix.

## Full-project fault audit and release follow-up (2026-09-27)

- Scope: reproduce local failures across installation, startup, configuration
  generation, Mihomo validation, NaiveProxy import/control, status polling and
  OpenKill-scoped UI styling before making bounded repairs. Preserve all
  protocol, DNS, proxy, node, subscription and user-YAML semantics.
- Risk boundary: controller and standalone-service changes must remain
  credential-free at the OpenKill boundary; UI changes must remain scoped to
  OpenKill routes. No legacy writer, parser grammar, ABI constant or network
  policy may change without direct evidence and a named contract.
- Validation: use local fixtures, behavior tests, the production-template
  browser harness, POSIX/BusyBox syntax checks, `sh scripts/local-gate.sh` and
  `git diff --check`. Temporary artifacts belong under `D:\openkill-cache`.
- Device boundary: the active plan forbids device, package-install, WAN/DNS,
  packet-path and VPS testing. Device and remote evidence remain pending even
  if local tests pass.
- Release boundary: after local gates and exact-commit Development CI pass,
  prepare one version increment, run the manual RC audit, then Formal Release
  with `release_gate=true` and `publish=true`. Preserve `v2026-1172-ipk` and
  its package as the rollback target.

### Fault-audit evidence (2026-09-27)

- The first full fast-matrix run reproduced a production-shadow failure rather
  than a device issue. The record-only harness always returned failure for
  `grep`, so a populated `china_ip_route.ipset` fixture was treated as empty;
  it also omitted the sourced OpenVPN helper APIs and the route-set rendering
  helpers. This produced unknown-command records and hid the route set from
  the parser.
- The bounded harness repair delegates only sandbox-contained route-file reads
  to the host `grep` and models the sourced helpers and generated pass-set
  files as record-only operations. It cannot execute OpenVPN, nft, UCI or any
  network command. Empty route fixtures remain an explicit
  `KNOWN_CURRENT_GAP`, matching production's fail-closed effective-policy
  behavior rather than being labelled a normalizer defect.
- `python scripts/test-production-shadow.py` now passes all 12 tests. Before
  committing the implementation change, rerun the fast matrix, the focused
  Naive/UI suites, POSIX/BusyBox checks, local gate and diff check. No device,
  package-install, WAN/DNS, packet-path or VPS test is authorized in this
  iteration.

### Development evidence and release preparation (2026-09-27)

- The bounded implementation commit is `b14bd903dbe8c498b331060699cc3ca3c415ed06`.
  Its exact OpenKill Development CI run
  [36313761351](https://github.com/dinggood615/openkill/actions/runs/36313761351)
  completed successfully.
- The clean local fast matrix run `20260927T104335Z-21592` passed all 19
  cases, including production shadow, NaiveProxy integration, UI contract,
  browser and preview suites. `wsl.exe sh scripts/local-gate.sh` and
  `git diff --check` also passed. Browser evidence remains local/mock-backend
  only; no device or remote endpoint was contacted.
- The release candidate increments the synchronized source version once from
  `2026-1172` to `2026-1173`. The previous `v2026-1172-ipk` package remains
  the rollback target. RC and Formal Release are still pending and must use
  the exact post-version-bump commit after its Development CI succeeds.

### 2026-1173 release evidence (2026-09-27)

- Source commit `5e2970ac32ac367bc67d15998d3838deb49157ad` passed the exact
  Development CI run
  [36314239111](https://github.com/dinggood615/openkill/actions/runs/36314239111).
- The manual RC Build for that exact source passed as run
  [36314303797](https://github.com/dinggood615/openkill/actions/runs/36314303797).
  Candidate IPK SHA256:
  `181fdc19698505f4e5939c5284e31c894c30ee6e9e012ef8e8cb95d483cacfb9`.
  Its audit reported valid package metadata, conffile preservation,
  maintainer-script deletion safety, no stale development references and no
  runtime sensitive/test-machine content.
- Formal Release run
  [36314524580](https://github.com/dinggood615/openkill/actions/runs/36314524580)
  completed successfully with `release_gate=true` and `publish=true`. The
  published package is
  [v2026-1173-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1173-ipk),
  asset `luci-app-openkill_2026-1173_all.ipk`, SHA256
  `9502a61918ff787272f1febeb8b485676bfd172f6f6a59ef0e60b61201c774b9`.
- The local fast matrix `20260927T105252Z-18244` passed 19/19, and the WSL
  local gate and diff check passed on the release commit. The browser run is
  local production-template/mock-backend evidence only. Device, independent
  binary installation, process/PID/listener, node credential, VPS and remote
  connectivity checks remain `设备待验证／远端待验证` under the active plan.
- Rollback remains the published `v2026-1172-ipk`; installing it preserves the
  existing OpenKill configuration, independent NaiveProxy data and user YAML.

### NaiveProxy status freshness repair (2026-09-27)

- User-visible evidence showed `loader-or-version-probe-failed` after the
  controller refresh.  The authorised diagnostic confirmed the installed
  binary is executable and `naive --version` exits successfully; the current
  bridge manifest rebuild reports `component_status=available`.
- Root cause: on this LuCI build `io.popen` is exposed but may be rejected in
  controller context.  `naive_read_manifest()` then read a stale runtime
  manifest whose former failure reason survived after the component became
  usable.  The bounded repair falls back to the fixed, local
  `luci.sys.exec()` manifest command before using the cached file.  It accepts
  no request data and does not alter OpenKill UCI, YAML, network policy or a
  node process.
- Next: run focused Naive/UI tests and the local gate, commit/push the repair,
  then replace the pending 2026-1175 release candidate with the exact repaired
  source commit.  The already completed RC run for `306aea6` is evidence for
  the earlier token-only candidate and is not release evidence for this repair.

### 2026-1175 release evidence (2026-09-27)

- Source commit `0e1b98dce39dc69d7a28dc0bac6d61bb72966015` passed exact
  Development CI run [36326267531](https://github.com/dinggood615/openkill/actions/runs/36326267531).
- The replacement RC audit passed as run
  [36326385147](https://github.com/dinggood615/openkill/actions/runs/36326385147),
  building `luci-app-openkill_2026-1175_all.ipk` (candidate SHA256
  `04bde69d1e3ea11cfdd43948132273857ce05bcdf59ca9edf35f11fcc123c82a`).
- Formal Release run [36326495615](https://github.com/dinggood615/openkill/actions/runs/36326495615)
  completed successfully with `release_gate=true` and `publish=true`.  Tag
  `v2026-1175-ipk` points to the exact source commit.  The published package
  SHA256 is `77433b384d99c3eab60d1934fcdca0a148bfbc1b92d0c25042056be04108ded1`.
- The test device was only read for diagnosis: its binary is executable and
  the version probe succeeds.  Package deployment, node start, owned listener
  verification and SOCKS5 HTTPS/VPS verification remain pending.

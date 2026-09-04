<h1 align="center">
  <img src="https://raw.githubusercontent.com/dinggood615/openkill/master/img/logo.png" alt="OpenKill" width="200">
  <br>OpenKill<br>
</h1>

OpenKill 是基于 OpenClash 源码的 OpenWrt 客户端项目。

当前版本：`2026-1002`。

许可：本项目遵循 [MIT License](LICENSE)，并保留上游 OpenClash 及相关组件的版权声明。

更新统一使用 `--update`，会更新 OpenKill 软件包并安装/更新官方稳定 Meta（Mihomo）内核。

2026-1002：完成第二、三阶段优化：watchdog 将网络地址扫描改为周期任务，降低后台开销；保留核心存活与防重启保护；DNS/IPv6 与代理测速继续使用 Mihomo 官方配置能力，避免额外常驻进程。

<h1 align="center">
  <img src="https://raw.githubusercontent.com/dinggood615/openkill/master/img/logo.png" alt="OpenKill" width="200">
  <br>OpenKill<br>
</h1>

OpenKill 是基于 OpenClash 源码的 OpenWrt 客户端项目。

当前版本：`2026-1003`。

许可：本项目遵循 [MIT License](LICENSE)，并保留上游 OpenClash 及相关组件的版权声明。

更新统一使用 `--update`，会更新 OpenKill 软件包并安装/更新官方稳定 Meta（Mihomo）内核。

2026-1003：默认启用 Mihomo TCP 并发连接与统一延迟测量，改善双栈测速和首连速度；watchdog 网络地址扫描按周期执行，降低后台开销。

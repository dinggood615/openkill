local m = Map("openkill", "NaiveProxy")
m.pageaction = true
m.description = "可选的官方 NaiveProxy 辅助组件。每个节点通过独立的 127.0.0.1 SOCKS5 入口加入现有 Mihomo 策略组。"
page_header_title = "NaiveProxy"
page_header_description = "组件、节点桥接与生命周期状态"

local s = m:section(NamedSection, "config", "openkill")
s.anonymous = true
s.addremove = false

local o = s:option(Flag, "naive_enabled", "启用 NaiveProxy 桥接")
o.default = "0"
o.rmempty = false
o.description = "关闭时不启动辅助进程，现有节点和透明接管行为保持不变。"

o = s:option(Flag, "naive_auto_start", "随 OpenKill 启动")
o.default = "1"
o.rmempty = false
o:depends("naive_enabled", "1")

o = s:option(Value, "naive_component_path", "组件路径")
o.default = "/etc/openkill/core/naive"
o.rmempty = false
o:depends("naive_enabled", "1")

o = s:option(Value, "naive_component_url", "官方组件 URL")
o.rmempty = true
o:depends("naive_enabled", "1")
o.description = "只接受 klzgrad/naiveproxy 官方 HTTPS 地址。"

o = s:option(Value, "naive_component_sha256", "组件 SHA256")
o.rmempty = true
o:depends("naive_enabled", "1")

o = s:option(Value, "naive_port_base", "回环端口起点")
o.default = "11080"
o.datatype = "port"
o.rmempty = false
o:depends("naive_enabled", "1")

local status = m:section(SimpleSection)
status.template = "openkill/naive_status"

return m

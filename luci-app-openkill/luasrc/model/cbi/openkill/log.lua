--
local NXFS = require "nixio.fs"
local SYS = require "luci.sys"
local HTTP = require "luci.http"

m = Map("openkill", translate("Server Logs"))
m.description = "查看插件、核心和调试运行日志。"
page_header_title = translate("Server Logs")
page_header_description = "查看插件、核心和调试运行日志。"
local page_header = m:section(SimpleSection)
page_header.template = "openkill/page_header"
page_header.title = translate("Server Logs")
page_header.description = "查看插件、核心和调试运行日志。"
s = m:section(TypedSection, "openkill")
m.pageaction = false
s.anonymous = true
s.addremove=false

log = s:option(TextValue, "clog")
log.readonly=true
log.pollcheck=true
log.template="openkill/log"
log.description = translate("")
log.rows = 29

m:append(Template("openkill/toolbar_show"))
m:append(Template("openkill/config_editor"))

return m

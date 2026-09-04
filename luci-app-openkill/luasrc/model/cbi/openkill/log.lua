--
local NXFS = require "nixio.fs"
local SYS = require "luci.sys"
local HTTP = require "luci.http"

m = Map("openkill", translate("Server Logs"))
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

local NXFS = require "nixio.fs"
local SYS = require "luci.sys"
local HTTP = require "luci.http"
local DISP = require "luci.dispatcher"
local UTIL = require "luci.util"
local fs = require "luci.openkill"
local uci = require("luci.model.uci").cursor()

m = SimpleForm("openkill",translate("OpenKill"))
m.description = nil
m.reset = false
m.submit = false

m:section(SimpleSection).template = "openkill/status"
m:append(Template("openkill/myip"))
m:append(Template("openkill/update"))
m:append(Template("openkill/config_edit"))
m:append(Template("openkill/config_upload"))

return m

-- Compatibility view retained for old LuCI bookmarks.  NaiveProxy node
-- credentials and lifecycle are owned by the standalone bridge; this CBI
-- intentionally exposes no OpenKill UCI fields.
local http = require "luci.http"
local dispatcher = require "luci.dispatcher"

http.redirect(dispatcher.build_url("admin", "services", "openkill", "settings") .. "?tab=compatibility#openkill-naive-component-info")

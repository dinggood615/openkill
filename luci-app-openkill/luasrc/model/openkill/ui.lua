-- Shared LuCI helpers used by OpenKill CBI pages.
-- Keeping this in one module prevents every page from embedding a copy of
-- the same DOM cleanup script.
local HTTP = require "luci.http"

local M = {}

function M.optimize_cbi_ui()
	local translate_fn = rawget(_G, "translate") or function(value) return value end
	HTTP.write([[
		<script type="text/javascript">
			(function() {
				var moveUp = "]] .. translate_fn("Move up") .. [[";
				var moveDown = "]] .. translate_fn("Move down") .. [[";
				document.querySelectorAll("input.btn.cbi-button.cbi-button-up").forEach(function(btn) {
					btn.value = moveUp;
				});
				document.querySelectorAll("input.btn.cbi-button.cbi-button-down").forEach(function(btn) {
					btn.value = moveDown;
				});
				document.querySelectorAll("div.cbi-value-description").forEach(function(descDiv) {
					var prev = descDiv.previousSibling;
					while (prev && prev.nodeType === Node.TEXT_NODE && prev.textContent.trim() === "") {
						prev = prev.previousSibling;
					}
					if (prev && prev.nodeType === Node.ELEMENT_NODE && prev.tagName === "BR") {
						prev.remove();
					}
				});
			})();
		</script>
	]])
end

return M

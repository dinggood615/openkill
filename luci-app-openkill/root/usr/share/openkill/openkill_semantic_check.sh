#!/bin/sh
# Semantic checks shared by the preflight validator and the running service.
# Mihomo's -t catches core-specific syntax; these checks catch references and
# types that are otherwise easy to break while OpenKill merges UCI settings.
set -eu

CONFIG_FILE="${1:-}"
[ -s "$CONFIG_FILE" ] || {
   echo "configuration file is missing or empty: ${CONFIG_FILE:-<unset>}" >&2
   exit 2
}

command -v ruby >/dev/null 2>&1 || exit 0

ruby -ryaml - "$CONFIG_FILE" <<'RUBY'
config = YAML.load_file(ARGV.fetch(0))
fail = lambda { |message| warn "semantic validation failed: #{message}"; exit 1 }
fail.call('top-level YAML value must be a mapping') unless config.is_a?(Hash)

bool = lambda do |key|
  value = config[key]
  next if value.nil?
  fail.call("#{key} must be true or false") unless value == true || value == false
end
%w[allow-lan ipv6 tcp-concurrent unified-delay].each(&bool)

if config.key?('external-controller')
  endpoint = config['external-controller'].to_s
  host, port = endpoint.match?(/^\[[^\]]+\]:\d+$/) ? endpoint.match(/^\[([^\]]+)\]:(\d+)$/).captures : endpoint.match(/^([^:]+):(\d+)$/)&.captures
  fail.call('external-controller must be host:port or [ipv6]:port') unless host && port
  fail.call('external-controller port is invalid') unless port.to_i.between?(1, 65535)
end

cors = config['external-controller-cors']
if cors.is_a?(Hash)
  origins = Array(cors['allow-origins'])
  fail.call('external-controller-cors must not use wildcard origins') if origins.include?('*')
end

if config.key?('mode')
  fail.call('mode is invalid') unless %w[rule global direct script].include?(config['mode'].to_s)
end
if config.key?('find-process-mode')
  fail.call('find-process-mode is invalid') unless %w[off strict always].include?(config['find-process-mode'].to_s)
end

proxy_names = []
proxies = config['proxies']
if proxies
  fail.call('proxies must be an array') unless proxies.is_a?(Array)
  proxies.each_with_index do |proxy, index|
    fail.call("proxies[#{index}] must be a mapping") unless proxy.is_a?(Hash)
    name = proxy['name'].to_s.strip
    type = proxy['type'].to_s.strip
    fail.call("proxies[#{index}] has no name") if name.empty?
    fail.call("proxies[#{index}] has no type") if type.empty?
    fail.call("duplicate proxy name: #{name}") if proxy_names.include?(name)
    proxy_names << name
    if proxy.key?('ip-version')
      allowed = %w[dual ipv4 ipv6 ipv4-prefer ipv6-prefer]
      fail.call("proxy #{name} has invalid ip-version") unless allowed.include?(proxy['ip-version'].to_s)
    end
  end
end

provider_names = []
providers = config['proxy-providers']
if providers
  fail.call('proxy-providers must be a mapping') unless providers.is_a?(Hash)
  providers.each do |name, provider|
    provider_name = name.to_s.strip
    fail.call('proxy provider name is empty') if provider_name.empty?
    fail.call("duplicate proxy provider: #{provider_name}") if provider_names.include?(provider_name)
    provider_names << provider_name
    fail.call("proxy provider #{provider_name} must be a mapping") unless provider.is_a?(Hash)
    if provider.key?('type')
      fail.call("proxy provider #{provider_name} has invalid type") unless %w[http file inline].include?(provider['type'].to_s)
    end
  end
end

group_names = []
groups = config['proxy-groups']
if groups
  fail.call('proxy-groups must be an array') unless groups.is_a?(Array)
  groups.each_with_index do |group, index|
    fail.call("proxy-groups[#{index}] must be a mapping") unless group.is_a?(Hash)
    name = group['name'].to_s.strip
    type = group['type'].to_s.strip
    fail.call("proxy-groups[#{index}] has no name") if name.empty?
    fail.call("proxy-groups[#{index}] has no type") if type.empty?
    fail.call("duplicate proxy-group name: #{name}") if group_names.include?(name)
    group_names << name
    if group.key?('proxies')
      fail.call("proxy-group #{name} proxies must be an array") unless group['proxies'].is_a?(Array)
    end
    if group.key?('interval')
      interval = group['interval'].to_i
      fail.call("proxy-group #{name} interval must be positive") if interval <= 0
    end
  end
  # Mihomo exposes these built-in outbound targets in addition to user
  # proxies/groups.  Accepting them keeps the preflight compatible with
  # imported rule sets without weakening the unknown-reference check.
  valid_targets = (proxy_names + group_names + %w[DIRECT REJECT REJECT-DROP PASS GLOBAL COMPATIBLE SYSTEM PROXY]).uniq
  groups.each do |group|
    Array(group['proxies']).each do |target|
      target_name = target.to_s
      fail.call("proxy-group #{group['name']} references unknown target #{target_name}") unless valid_targets.include?(target_name)
    end
  end
end

dns = config['dns']
if dns
  fail.call('dns must be a mapping') unless dns.is_a?(Hash)
  if dns['enable'] == true && Array(dns['nameserver']).empty?
    fail.call('dns.nameserver must not be empty when DNS is enabled')
  end
  respect = dns['respect-rules'] == true || dns['respect-rules'].to_s == 'true'
  if respect && Array(dns['proxy-server-nameserver']).empty?
    fail.call('dns.proxy-server-nameserver is required when dns.respect-rules is enabled')
  end
  fail.call('dns.ipv6 cannot be enabled while top-level ipv6 is disabled') if dns['ipv6'] == true && config['ipv6'] == false
  if dns['enable'] == true
    listen = dns['listen'].to_s
    fail.call('dns.listen is required when DNS is enabled') if listen.empty?
  end
end

tun = config['tun']
if tun
  fail.call('tun must be a mapping') unless tun.is_a?(Hash)
  if tun.key?('stack')
    fail.call('tun.stack is invalid') unless %w[system gvisor mixed].include?(tun['stack'].to_s)
  end
  # Routing and transparent firewall programming have one owner.  The shell
  # service exports the selected UCI mode for this check; standalone callers
  # can still be validated safely by falling back to the OpenKill-owned mode.
  tun_owner = ENV['OPENKILL_TUN_OWNER'].to_s
  if tun_owner.empty? && File.executable?('/sbin/uci')
    tun_owner = `uci -q get openkill.config.tun_owner 2>/dev/null`.to_s.strip
  end
  tun_owner = 'openkill' unless %w[openkill mihomo].include?(tun_owner)
  auto_route = tun['auto-route'] == true
  auto_redirect = tun['auto-redirect'] == true
  if tun_owner == 'openkill'
    fail.call('OpenKill-owned mode requires tun.auto-route=false and tun.auto-redirect=false') if auto_route || auto_redirect
  elsif !auto_route || !auto_redirect
    fail.call('Mihomo-native mode requires tun.auto-route=true and tun.auto-redirect=true')
  end
end

puts 'semantic validation passed'
RUBY

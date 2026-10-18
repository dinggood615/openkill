# frozen_string_literal: true

# Keep Telegram's UDP path separate from the user's ordinary Telegram
# selector.  A select group can legitimately point at a TCP-only node while
# web sites still work, but Telegram media/calls and some DC transports need a
# proxy which advertises UDP support.  This module only adds protocol-scoped
# rules; it never changes the user's selected group or the default business
# routing.
module OpenKillTelegramCompat
  MANAGED_PREFIX = 'OpenKill-Telegram-UDP'
  PROBE_URL = 'https://cp.cloudflare.com/generate_204'

  TELEGRAM_DOMAIN_RE = /(?:telegram(?:\.org|\.me|\.dog)|t\.me|tdesktop\.com|telegra\.ph|telesco\.pe|telegram-cdn\.org|cdn-telegram\.org)/i
  TELEGRAM_IP_RE = /\A(?:91\.(?:108|105|109|102)\.|149\.154\.160\.|185\.76\.151\.|2001:67c:4e8:|2001:b28:f23)/i

  module_function

  def apply(config, state_path = '/tmp/openkill-telegram-udp.state')
    unless config.is_a?(Hash)
      write_state(state_path, 'enabled=0', 'reason=invalid-config', 'udp_nodes=0', 'rules=0')
      return config
    end

    rules = Array(config['rules']).map(&:to_s)
    telegram_rules = rules.select { |rule| telegram_route_rule?(rule) }
    groups = Array(config['proxy-groups']).select { |group| group.is_a?(Hash) }
    existing_managed = groups.find { |group| managed_group?(group) }
    candidates = udp_capable_proxies(config)

    if telegram_rules.empty?
      remove_managed_path(config, existing_managed)
      write_state(state_path, 'enabled=0', 'reason=no-telegram-rules', 'udp_nodes=0', 'rules=0')
      return config
    end

    if candidates.empty?
      remove_managed_path(config, existing_managed)
      write_state(state_path, 'enabled=0', 'reason=no-udp-capable-proxy', 'udp_nodes=0', 'rules=0')
      log_warn('Telegram UDP path unavailable: no concrete UDP-capable proxy was found')
      return config
    end

    managed_name = ensure_managed_group(config, groups, existing_managed, candidates)
    generated = 0
    rewritten = []
    rules.each do |rule|
      if telegram_route_rule?(rule) && !udp_rule?(rule)
        udp_rule = protocol_rule(rule, managed_name)
        unless udp_rule.nil? || rules.include?(udp_rule) || rewritten.include?(udp_rule)
          rewritten << udp_rule
          generated += 1
        end
      end
      rewritten << rule
    end
    config['rules'] = rewritten.uniq
    write_state(state_path, 'enabled=1', 'reason=udp-policy-ready', "group=#{managed_name}", "udp_nodes=#{candidates.length}",
                "rules=#{generated}", "updated=#{Time.now.utc.strftime('%Y-%m-%dT%H:%M:%SZ')}")
    log_tip('Telegram UDP path prepared with %d UDP-capable proxy nodes and %d protocol rules' %
      [candidates.length, generated])
    config
  rescue StandardError => e
    write_state(state_path, 'enabled=0', 'reason=compatibility-error', 'udp_nodes=0', 'rules=0')
    log_warn('Telegram UDP path preparation failed: %s' % e.message.to_s[0, 160])
    config
  end

  def udp_capable_proxies(config)
    concrete = Array(config['proxies']).select do |proxy|
      proxy.is_a?(Hash) && truthy?(proxy['udp']) && !proxy['name'].to_s.empty? &&
        !%w[DIRECT REJECT PASS COMPATIBLE GLOBAL].include?(proxy['name'].to_s.upcase)
    end.map { |proxy| proxy['name'].to_s }.uniq
    return concrete unless concrete.empty?

    # Provider-backed configurations do not expose their expanded members in
    # the generated YAML.  Reuse an explicitly named UDP group when it is
    # present, without changing that group's selection.  Groups containing an
    # explicit DIRECT/REJECT member are rejected to avoid silently bypassing
    # Telegram's transport policy.
    groups = Array(config['proxy-groups']).select { |group| group.is_a?(Hash) }
    by_name = groups.each_with_object({}) { |group, result| result[group['name'].to_s] = group }
    candidates = groups.select do |group|
      name = group['name'].to_s
      type = group['type'].to_s.downcase
      name.downcase.include?('udp') &&
        !managed_group?(group) &&
        %w[select fallback url-test load-balance].include?(type) &&
        !Array(group['proxies']).empty? &&
        safe_udp_group?(name, by_name)
    end.sort_by do |group|
      type_rank = {'fallback' => 0, 'url-test' => 1, 'load-balance' => 2, 'select' => 3}[group['type'].to_s.downcase] || 4
      [type_rank, group['name'].to_s]
    end
    candidates.empty? ? [] : [candidates.first['name'].to_s]
  end

  def safe_udp_group?(name, groups, visiting = {})
    return false if visiting[name]
    group = groups[name]
    return false unless group.is_a?(Hash)
    visiting[name] = true
    refs = Array(group['proxies']).map(&:to_s)
    return false if refs.empty? || refs.any? { |ref| %w[DIRECT REJECT REJECT-DROP PASS COMPATIBLE GLOBAL].include?(ref.upcase) }
    refs.all? { |ref| groups.key?(ref) ? safe_udp_group?(ref, groups, visiting.dup) : true }
  end

  def ensure_managed_group(config, groups, existing, candidates)
    group = existing
    unless group
      names = groups.map { |item| item['name'].to_s } + Array(config['proxies']).map { |item| item.is_a?(Hash) ? item['name'].to_s : '' }
      name = unique_name(names)
      group = {
        'name' => name,
        'type' => 'fallback',
        'url' => PROBE_URL,
        'interval' => 180,
        'timeout' => 5000,
        'max-failed-times' => 2,
        'lazy' => false,
        'expected-status' => 204,
        'proxies' => candidates
      }
      config['proxy-groups'] ||= []
      config['proxy-groups'] << group
    end
    group['proxies'] = candidates
    group['type'] = 'fallback'
    group['url'] = PROBE_URL
    group['interval'] = 180
    group['timeout'] = 5000
    group['max-failed-times'] = 2
    group['lazy'] = false
    group['expected-status'] = 204
    group['name'].to_s
  end

  def unique_name(names)
    base = MANAGED_PREFIX
    return base unless names.include?(base)
    index = 1
    index += 1 while names.include?("#{base}-#{index}")
    "#{base}-#{index}"
  end

  def managed_group?(group)
    name = group['name'].to_s
    name.start_with?(MANAGED_PREFIX) && group['type'].to_s.downcase == 'fallback' &&
      group['url'].to_s == PROBE_URL
  end

  def remove_managed_path(config, group)
    return unless group
    name = group['name'].to_s
    config['proxy-groups'] = Array(config['proxy-groups']).reject { |item| item.equal?(group) }
    config['rules'] = Array(config['rules']).reject do |rule|
      udp_rule?(rule.to_s) && rule.to_s.split(',').last.to_s == name
    end
  end

  def telegram_route_rule?(rule)
    parts = rule.to_s.split(',').map { |part| part.strip }
    return false if parts.length < 3
    type = parts[0].to_s.upcase
    value = parts[1].to_s
    if type == 'RULE-SET'
      return value.match?(TELEGRAM_DOMAIN_RE)
    end
    return false unless %w[DOMAIN DOMAIN-SUFFIX DOMAIN-KEYWORD GEOSITE IP-CIDR IP-CIDR6 IP-SUFFIX].include?(type)
    value.match?(TELEGRAM_DOMAIN_RE) || value.match?(TELEGRAM_IP_RE) || value.downcase == 'telegram'
  end

  def protocol_rule(rule, group)
    parts = rule.to_s.split(',').map { |part| part.strip }
    return nil if parts.length < 3
    suffix = %w[no-resolve src].include?(parts.last.to_s.downcase) ? parts.pop : nil
    target = parts.pop
    return nil if target.to_s.empty? || %w[DIRECT REJECT REJECT-DROP PASS COMPATIBLE].include?(target.to_s.upcase)
    matcher = parts.join(',')
    return nil if matcher.empty?
    matcher += ",#{suffix}" unless suffix.nil?
    "AND,((NETWORK,UDP),(#{matcher})),#{group}"
  end

  def udp_rule?(rule)
    rule.to_s.match?(/\AAND,\(\(NETWORK,UDP\),\(/i)
  end

  def truthy?(value)
    [true, 1, '1', 'true', 'yes', 'on'].include?(value) || value.to_s.downcase == 'udp'
  end

  def write_state(path, *lines)
    directory = File.dirname(path)
    Dir.mkdir(directory) unless Dir.exist?(directory)
    tmp = "#{path}.tmp.#{$$}"
    File.open(tmp, 'w', 0o600) { |file| file.write(lines.join("\n") + "\n") }
    File.rename(tmp, path)
  rescue StandardError
    nil
  end

  def log_tip(message)
    if defined?(YAML) && YAML.respond_to?(:LOG_TIP)
      YAML.LOG_TIP(message)
    end
  end

  def log_warn(message)
    if defined?(YAML) && YAML.respond_to?(:LOG_WARN)
      YAML.LOG_WARN(message)
    end
  end
end

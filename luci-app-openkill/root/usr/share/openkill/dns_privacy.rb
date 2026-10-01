# DNS profile transformation; never changes network policy or user groups.
module OpenKillDnsPrivacy
  BOOTSTRAP = ['https://1.1.1.1/dns-query', 'https://223.5.5.5/dns-query'].freeze
  def self.upstream(server, group = nil)
    text = server.to_s
    raise ArgumentError, 'DNS upstream must use authenticated encryption' unless text.match?(/\A(?:https|tls|quic|h3):\/\//i)
    raise ArgumentError, 'Unsafe DNS certificate/ECS parameter' if text.match?(/(?:skip-cert-verify|ecs(?:-override)?)=/i)
    base, suffix = text.split('#', 2)
    raise ArgumentError, 'Ambiguous DNS upstream' if base.match?(/[\s\x00-\x1f]/)
    if suffix
      tokens = suffix.split('&')
      raise ArgumentError, 'Unsupported DNS upstream parameter' if tokens.any? { |x| x.include?('=') }
      raise ArgumentError, 'Ambiguous DNS upstream selector' if tokens.size > 1
    end
    return base + '#' + group if group
    base
  end
  def self.apply(value, mode, group)
    dns = value.fetch('dns')
    if mode == 'strict'
      raise ArgumentError, 'Invalid DNS group name' unless group.match?(/\A[A-Za-z0-9_-]{1,64}\z/)
      groups = value['proxy-groups'] ||= []
      raise ArgumentError, 'DNS group name conflicts with existing profile' if groups.any? { |g| g['name'] == group } || Array(value['proxies']).any? { |p| p['name'] == group }
      # Only concrete nodes: no nested groups, providers or implicit DIRECT.
      # Provider-only profiles require explicit materialization before strict mode.
      nodes = Array(value['proxies']).select do |p|
        p.is_a?(Hash) && !p['name'].to_s.empty? &&
          !%w[direct reject dns].include?(p['type'].to_s.downcase) &&
          !%w[DIRECT REJECT GLOBAL COMPATIBLE PASS].include?(p['name']) &&
          !p['server'].to_s.match?(/\A(?:localhost|127\.|::1|\[::1\])/i) &&
          p['dialer-proxy'].to_s.empty?
      end.map { |p| p['name'] }.uniq
      raise ArgumentError, 'Strict DNS requires concrete proxy nodes without dialer dependencies' if nodes.empty?
      groups << {'name'=>group, 'type'=>'select', 'proxies'=>nodes}
      %w[nameserver fallback direct-nameserver].each do |key|
        next unless dns.key?(key)
        dns[key] = Array(dns[key]).map { |s| upstream(s, group) }.uniq
      end
      if dns['nameserver-policy'].is_a?(Hash)
        dns['nameserver-policy'].transform_values! { |v| Array(v).map { |s| upstream(s,group) }.uniq }
      end
      dns['respect-rules'] = false
    end
    # Direct, IP-literal, certificate-verified bootstrap avoids proxy recursion.
    dns['default-nameserver'] = BOOTSTRAP.dup
    dns['proxy-server-nameserver'] = BOOTSTRAP.dup
    if dns['proxy-server-nameserver-policy'].is_a?(Hash)
      dns['proxy-server-nameserver-policy'].transform_values! { |_v| BOOTSTRAP.dup }
    end
    value
  end
end

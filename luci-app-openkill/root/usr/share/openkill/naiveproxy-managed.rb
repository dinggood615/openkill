#!/usr/bin/env ruby
# Merge only explicitly selected, credential-free loopback endpoints into the
# staged Mihomo YAML. The caller validates the complete config before commit.
require 'yaml'
require 'tempfile'

def managed_groups(config_path)
  config = YAML.safe_load(File.read(config_path), permitted_classes: [], permitted_symbols: [], aliases: true)
  raise 'invalid configuration root' unless config.is_a?(Hash)
  groups = config['proxy-groups'] || []
  raise 'invalid proxy groups' unless groups.is_a?(Array)
  names = groups.map do |group|
    next unless group.is_a?(Hash) && %w[select url-test fallback load-balance].include?(group['type'])
    name = group['name']
    next unless name.is_a?(String) && !name.empty? && !name.match?(/[[:cntrl:]]/)
    next if %w[DIRECT REJECT GLOBAL].include?(name)
    name
  end.compact
  names.uniq.select { |name| names.count(name) == 1 }
end

def merge_managed(config_path, selection_path, port_map, node_dir)
  return unless File.file?(selection_path)
  selected = []
  File.foreach(selection_path) do |line|
    line = line.strip
    next if line.empty?
    match = /\A([A-Za-z0-9_-]{1,80}) ([0-9]{1,5})(?: (.+))?\z/.match(line)
    raise 'invalid managed selection' unless match
    id, port = match[1], match[2].to_i
    raise 'invalid managed port' unless (1..65_535).cover?(port)
    raise 'duplicate managed identity or port' if selected.any? { |x| x[0] == id || x[1] == port }
    group = match[3]
    raise 'invalid strategy group' if group && (group.bytesize > 160 || group.match?(/[[:cntrl:]]/))
    selected << [id, port, group]
    raise 'too many managed nodes' if selected.length > 100
  end
  return if selected.empty?
  mappings = File.readlines(port_map, chomp: true)
  selected.each do |id, port, _group|
    raise 'missing node or changed port' unless File.file?(File.join(node_dir, "#{id}.json")) &&
                                               mappings.count("#{id} #{port}") == 1
    raise 'duplicate port mapping' unless mappings.count { |line| line.split.last == port.to_s } == 1
  end
  config = YAML.safe_load(File.read(config_path), permitted_classes: [], permitted_symbols: [], aliases: true)
  raise 'invalid configuration root' unless config.is_a?(Hash)
  proxies = config['proxies'] || []
  groups = config['proxy-groups'] || []
  providers = config['proxy-providers'] || {}
  raise 'invalid proxy definitions' unless proxies.is_a?(Array) && groups.is_a?(Array) && providers.is_a?(Hash)
  occupied = proxies.map { |p| p['name'] if p.is_a?(Hash) }.compact +
             groups.map { |g| g['name'] if g.is_a?(Hash) }.compact + providers.keys + %w[DIRECT REJECT GLOBAL]
  ports = {}
  mappings.each do |line|
    parts = line.split
    ports[parts[1]] = true if parts.length == 2 && parts[0].match?(/\A[A-Za-z0-9_-]{1,80}\z/) && parts[1].match?(/\A[0-9]{1,5}\z/)
  end
  # Re-running the merge against its own output is safe. Only exact loopback
  # endpoints backed by this component's stable port map are considered owned.
  managed_names = {}
  proxies.reject! do |proxy|
    next false unless proxy.is_a?(Hash) && proxy['name'].to_s.match?(/\AOpenKill-Naive-[A-Za-z0-9_-]{1,80}\z/)
    if proxy['type'] == 'socks5' && proxy['server'] == '127.0.0.1' && proxy['udp'] == false && ports[proxy['port'].to_s]
      managed_names[proxy['name']] = true
      true
    else
      false
    end
  end
  groups.each do |group|
    next unless group.is_a?(Hash) && group['proxies'].is_a?(Array)
    group['proxies'].reject! { |name| managed_names[name] }
  end
  selected.each do |id, port, group_name|
    name = "OpenKill-Naive-#{id}"
    raise 'managed node name conflict' if occupied.include?(name) && !managed_names[name]
    if group_name
      matches = groups.select { |group| group.is_a?(Hash) && group['name'] == group_name }
      raise 'strategy group missing or ambiguous' unless matches.length == 1
      target = matches.first
      raise 'unsupported strategy group type' unless %w[select url-test fallback load-balance].include?(target['type'])
      target['proxies'] ||= []
      raise 'invalid strategy group members' unless target['proxies'].is_a?(Array)
      target['proxies'] << name unless target['proxies'].include?(name)
    end
    proxies << { 'name' => name, 'type' => 'socks5', 'server' => '127.0.0.1', 'port' => port, 'udp' => false }
    occupied << name
  end
  config['proxies'] = proxies
  Tempfile.create(['.naive-managed-', '.yaml'], File.dirname(config_path)) do |temp|
    temp.chmod(File.stat(config_path).mode & 0o777)
    temp.write(YAML.dump(config))
    temp.flush
    temp.fsync
    File.rename(temp.path, config_path)
  end
end

if $PROGRAM_NAME == __FILE__
  begin
    if ARGV.length == 2 && ARGV[0] == '--list-groups'
      managed_groups(ARGV[1]).each { |name| puts name }
    else
      raise 'expected config, selection, port map and node directory' unless ARGV.length == 4
      merge_managed(*ARGV)
    end
  rescue StandardError
    warn 'Naive managed integration failed: invalid selection, name conflict, or invalid YAML'
    exit 1
  end
end

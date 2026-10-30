#!/usr/bin/env ruby
# Merge only explicitly selected, credential-free loopback endpoints into the
# staged Mihomo YAML. The caller validates the complete config before commit.
require 'yaml'
require 'tempfile'

def merge_managed(config_path, selection_path, port_map, node_dir)
  return unless File.file?(selection_path)
  selected = []
  File.foreach(selection_path) do |line|
    line = line.strip
    next if line.empty?
    match = /\A([A-Za-z0-9_-]{1,80}) ([0-9]{1,5})\z/.match(line)
    raise 'invalid managed selection' unless match
    id, port = match[1], match[2].to_i
    raise 'invalid managed port' unless (1..65_535).cover?(port)
    raise 'duplicate managed identity or port' if selected.any? { |x| x[0] == id || x[1] == port }
    selected << [id, port]
    raise 'too many managed nodes' if selected.length > 100
  end
  return if selected.empty?
  mappings = File.readlines(port_map, chomp: true)
  selected.each do |id, port|
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
  selected.each do |id, port|
    name = "OpenKill-Naive-#{id}"
    raise 'managed node name conflict' if occupied.include?(name)
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
    raise 'expected config, selection, port map and node directory' unless ARGV.length == 4
    merge_managed(*ARGV)
  rescue StandardError
    warn 'Naive managed integration failed: invalid selection, name conflict, or invalid YAML'
    exit 1
  end
end

#!/usr/bin/env ruby
require 'yaml'

def endpoint(value)
  match = /\A(?:\[([^\]]+)\]|([^:]+)):(\d+)\z/.match(value.to_s)
  raise 'missing or invalid listener' unless match
  host = match[1] || match[2]
  host = '127.0.0.1' if host == '0.0.0.0'
  host = '::1' if host == '::'
  ipv6 = host.include?(':')
  if ipv6
    raise 'invalid IPv6 listener' unless host.match?(/\A[0-9a-fA-F:]+\z/)
  else
    parts = host.split('.')
    raise 'invalid IPv4 listener' unless parts.length == 4 && parts.all? { |p| p.match?(/\A\d+\z/) && p.to_i <= 255 }
  end
  port = Integer(match[3])
  raise 'invalid port' unless (1..65535).cover?(port)
  "#{ipv6 ? "[#{host}]" : host}:#{port}"
end

if $PROGRAM_NAME == __FILE__
  value = YAML.load_file(ARGV.fetch(0))
  secret = value.fetch('secret', '').to_s
  raise 'multiline secret is invalid' if secret.match?(/[\r\n\x00]/)
  tun = value.fetch('tun', {}) || {}
  device = tun['enable'] == true ? tun.fetch('device', 'utun').to_s : ''
  raise 'invalid TUN device' unless device.empty? || device.match?(/\A[a-zA-Z0-9_.-]{1,15}\z/)
  table = Integer(tun.fetch('iproute2-table-index', 2022))
  raise 'invalid TUN route table' unless (1..4294967295).cover?(table)
  dns = value.fetch('dns', {}) || {}
  puts "http://#{endpoint(value['external-controller'])}", secret, device, table,
       (dns['enable'] == true ? endpoint(dns['listen']) : '')
end

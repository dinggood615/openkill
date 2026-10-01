require 'minitest/autorun'
require_relative '../luci-app-openkill/root/usr/share/openkill/dns_privacy'

class DnsPrivacyTest < Minitest::Test
  def profile
    {'proxies'=>[{'name'=>'fixture','type'=>'ss','server'=>'192.0.2.1'}],
     'proxy-groups'=>[{'name'=>'existing','type'=>'select','proxies'=>['DIRECT','fixture']}],
     'dns'=>{'nameserver'=>['https://dns.example/dns-query#RULES']}}
  end
  def test_dedicated_group_never_imports_nested_direct
    v=profile
    OpenKillDnsPrivacy.apply(v, 'strict', 'OpenKill-DNS')
    assert_equal ['fixture'], v['proxy-groups'].last['proxies']
    assert_equal ['DIRECT','fixture'], v['proxy-groups'].first['proxies']
    assert_equal ['https://dns.example/dns-query#OpenKill-DNS'], v['dns']['nameserver']
    assert v['dns']['default-nameserver'].all? { |x| x.start_with?('https://') }
  end
  def test_collision_rejected
    v=profile
    assert_raises(ArgumentError) { OpenKillDnsPrivacy.apply(v,'strict','existing') }
  end
  def test_no_proxy_rejected
    v=profile; v['proxies']=[]
    assert_raises(ArgumentError) { OpenKillDnsPrivacy.apply(v,'strict','OpenKill-DNS') }
  end
  def test_unsafe_dns_rejected
    ['https://dns.example/dns-query#skip-cert-verify=true',
     'https://dns.example/dns-query#ecs=192.0.2.0/24'].each do |upstream|
      v=profile; v['dns']['nameserver']=[upstream]
      assert_raises(ArgumentError) { OpenKillDnsPrivacy.apply(v,'strict','OpenKill-DNS') }
    end
  end
  def test_plain_bootstrap_replaced
    v=profile; v['dns']['proxy-server-nameserver']=['114.114.114.114#eth1']
    OpenKillDnsPrivacy.apply(v,'strict','OpenKill-DNS')
    assert_equal OpenKillDnsPrivacy::BOOTSTRAP, v['dns']['proxy-server-nameserver']
  end
  def test_local_socks_bridge_excluded_to_avoid_external_dns_cycle
    v=profile
    v['proxies'] << {'name'=>'local-bridge','type'=>'socks5','server'=>'127.0.0.1'}
    OpenKillDnsPrivacy.apply(v,'strict','OpenKill-DNS')
    assert_equal ['fixture'],v['proxy-groups'].last['proxies']
  end
end

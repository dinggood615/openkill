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
  def test_rules_selector_is_replaced_while_safe_connection_parameter_survives
    v=profile
    v['dns']['nameserver']=['https://dns.example/dns-query#RULES&h3=true']
    OpenKillDnsPrivacy.apply(v,'strict','OpenKill-DNS')
    assert_equal ['https://dns.example/dns-query#OpenKill-DNS&h3=true'], v['dns']['nameserver']
    assert OpenKillDnsPrivacy.strict_routed?(v['dns']['nameserver'].first, 'OpenKill-DNS')
  end
  def test_explicit_competing_selector_is_rejected_instead_of_silently_rewritten
    v=profile
    v['dns']['nameserver']=['https://dns.example/dns-query#wan']
    error=assert_raises(ArgumentError) { OpenKillDnsPrivacy.apply(v,'strict','OpenKill-DNS') }
    assert_match(/explicit upstream selector/, error.message)
  end
  def test_multiple_selectors_are_rejected_but_single_selector_with_parameters_is_valid
    assert_raises(ArgumentError) { OpenKillDnsPrivacy.parts('https://dns.example/dns-query#RULES&wan') }
    base, selector, parameters=OpenKillDnsPrivacy.parts('https://dns.example/dns-query#RULES&disable-ipv6=true')
    assert_equal 'https://dns.example/dns-query', base
    assert_equal 'RULES', selector
    assert_equal ['disable-ipv6=true'], parameters
  end
  def test_local_socks_bridge_excluded_to_avoid_external_dns_cycle
    v=profile
    v['proxies'] << {'name'=>'local-bridge','type'=>'socks5','server'=>'127.0.0.1'}
    OpenKillDnsPrivacy.apply(v,'strict','OpenKill-DNS')
    assert_equal ['fixture'],v['proxy-groups'].last['proxies']
  end

  def test_provider_backed_profile_uses_provider_without_inventing_direct
    v = profile
    v['proxies'] = []
    v['proxy-providers'] = {
      'subscription' => {'type' => 'file', 'path' => './proxy_provider/subscription.yaml'}
    }
    OpenKillDnsPrivacy.apply(v, 'strict', 'OpenKill-DNS')
    managed = v['proxy-groups'].last
    assert_equal ['subscription'], managed['use']
    assert_nil managed['proxies']
    assert_equal ['https://dns.example/dns-query#OpenKill-DNS'], v['dns']['nameserver']
  end
end

require 'minitest/autorun'
require_relative '../luci-app-openkill/root/usr/share/openkill/telegram_compat'

class TelegramCompatTest < Minitest::Test
  def fixture
    {
      'proxies' => [
        {'name' => 'tcp-node', 'udp' => false},
        {'name' => 'udp-node', 'udp' => true}
      ],
      'proxy-groups' => [{'name' => 'Telegram', 'type' => 'select', 'proxies' => ['tcp-node']}],
      'rules' => [
        'DOMAIN-SUFFIX,telegram.org,Telegram',
        'IP-CIDR,149.154.160.0/20,Telegram,no-resolve',
        'MATCH,DIRECT'
      ]
    }
  end

  def test_adds_managed_udp_group_and_protocol_rules_without_changing_tcp_rule
    value = fixture
    state_path = '/tmp/openkill-telegram-compat-test.state'
    OpenKillTelegramCompat.apply(value, state_path)
    managed = value['proxy-groups'].find { |group| group['name'] == 'OpenKill-Telegram-UDP' }
    refute_nil managed
    assert_equal ['udp-node'], managed['proxies']
    assert_match(/^reason=udp-policy-ready$/, File.read(state_path).lines.map(&:chomp).find { |line| line.start_with?('reason=') })
    assert_includes value['rules'], 'DOMAIN-SUFFIX,telegram.org,Telegram'
    assert_includes value['rules'], 'AND,((NETWORK,UDP),(DOMAIN-SUFFIX,telegram.org)),OpenKill-Telegram-UDP'
    assert_includes value['rules'], 'AND,((NETWORK,UDP),(IP-CIDR,149.154.160.0/20,no-resolve)),OpenKill-Telegram-UDP'
  end

  def test_is_idempotent
    value = fixture
    OpenKillTelegramCompat.apply(value)
    first = Marshal.load(Marshal.dump(value))
    OpenKillTelegramCompat.apply(value)
    assert_equal first, value
  end

  def test_does_not_create_a_direct_fallback_without_udp_nodes
    value = fixture
    value['proxies'][1]['udp'] = false
    OpenKillTelegramCompat.apply(value)
    refute value['proxy-groups'].any? { |group| group['name'].to_s.start_with?('OpenKill-Telegram-UDP') }
    refute value['rules'].any? { |rule| rule.start_with?('AND,((NETWORK,UDP),') }
  end

  def test_uses_an_explicit_udp_group_when_members_are_provider_backed
    value = fixture
    value['proxies'] = [{'name' => 'tcp-node', 'udp' => false}]
    value['proxy-groups'] << {'name' => 'UDP自动组', 'type' => 'fallback', 'proxies' => ['tcp-node']}
    OpenKillTelegramCompat.apply(value)
    managed = value['proxy-groups'].find { |group| group['name'] == 'OpenKill-Telegram-UDP' }
    assert_equal ['UDP自动组'], managed['proxies']
  end

  def test_respects_name_collision_with_an_existing_group
    value = fixture
    value['proxy-groups'] << {'name' => 'OpenKill-Telegram-UDP', 'type' => 'select', 'proxies' => ['tcp-node']}
    OpenKillTelegramCompat.apply(value)
    managed = value['proxy-groups'].find { |group| group['type'] == 'fallback' && group['url'] == OpenKillTelegramCompat::PROBE_URL }
    assert_equal 'OpenKill-Telegram-UDP-1', managed['name']
  end

  def test_removes_stale_managed_path_when_udp_capability_disappears
    value = fixture
    OpenKillTelegramCompat.apply(value)
    value['proxies'][1]['udp'] = false
    OpenKillTelegramCompat.apply(value)
    refute value['proxy-groups'].any? { |group| group['name'].to_s.start_with?('OpenKill-Telegram-UDP') && group['type'] == 'fallback' }
    refute value['rules'].any? { |rule| rule.start_with?('AND,((NETWORK,UDP),') }
  end
end

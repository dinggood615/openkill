require 'minitest/autorun'

class HealthDefaultsTest < Minitest::Test
  def normalize(group, urltest_override = false)
    source = File.read(File.join(__dir__, '../luci-app-openkill/root/usr/share/openkill/yml_change.sh'))
    start = source.index("         group['url'] =")
    finish = source.index("\n      end\n   end\n   # Provider-backed", start)
    urltest_address_override = urltest_override
    managed_probe_url = 'https://cp.cloudflare.com/generate_204'
    legacy_probe_url = 'https://www.gstatic.com/generate_204'
    snippet = source[start...finish]
    eval(snippet, binding)
    group
  end

  def test_custom_200_endpoint_does_not_inherit_204_expectation
    group = normalize({'type'=>'url-test', 'url'=>'https://fixture.example/health'})
    refute group.key?('expected-status')
  end

  def test_default_probe_uses_matching_204
    group = normalize({'type'=>'url-test'})
    assert_equal 'https://cp.cloudflare.com/generate_204', group['url']
    assert_equal 204, group['expected-status']
    assert_equal false, group['lazy']
  end

  def test_explicit_expected_status_and_lazy_survive
    group = normalize({'type'=>'fallback', 'url'=>'https://fixture.example/health', 'expected-status'=>'200-299', 'lazy'=>true})
    assert_equal '200-299', group['expected-status']
    assert_equal true, group['lazy']
  end

  def test_custom_probe_legacy_tuple_remains_user_owned
    group = normalize({'type'=>'url-test', 'url'=>'https://fixture.example/health', 'interval'=>300, 'timeout'=>5000, 'max-failed-times'=>3, 'lazy'=>true})
    assert_equal 300, group['interval']
    assert_equal true, group['lazy']
  end

  def test_legacy_openkill_probe_tuple_migrates_to_current_endpoint
    group = normalize({'type'=>'url-test', 'url'=>'https://www.gstatic.com/generate_204', 'expected-status'=>204,
                       'interval'=>180, 'timeout'=>3500, 'max-failed-times'=>2, 'lazy'=>false})
    assert_equal 'https://cp.cloudflare.com/generate_204', group['url']
    assert_equal 204, group['expected-status']
  end

  def test_explicit_legacy_endpoint_is_preserved_when_override_is_enabled
    group = normalize({'type'=>'url-test', 'url'=>'https://www.gstatic.com/generate_204', 'expected-status'=>204,
                       'interval'=>180, 'timeout'=>3500, 'max-failed-times'=>2, 'lazy'=>false}, true)
    assert_equal 'https://www.gstatic.com/generate_204', group['url']
  end

  def test_provider_health_migration_is_present_in_the_generator
    source = File.read(File.join(__dir__, '../luci-app-openkill/root/usr/share/openkill/yml_change.sh'))
    assert_includes source, "Value['proxy-providers'].is_a?(Hash)"
    assert_includes source, "health['url'] = managed_probe_url"
  end
end

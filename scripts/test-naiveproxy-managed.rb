require 'minitest/autorun'
require 'tmpdir'
require 'yaml'
require 'fileutils'
require_relative '../luci-app-openkill/root/usr/share/openkill/naiveproxy-managed'

class NaiveManagedTest < Minitest::Test
  def setup
    @dir = Dir.mktmpdir('naive-managed-')
    @config = File.join(@dir, 'config.yaml')
    @selection = File.join(@dir, 'selection')
    @ports = File.join(@dir, 'ports')
    File.write(@ports, "a 11080\nb 11081\n")
    File.write(File.join(@dir, 'a.json'), '{}')
    File.write(File.join(@dir, 'b.json'), '{}')
    @base = { 'proxies' => [{ 'name' => 'user-node', 'type' => 'direct' }],
              'proxy-groups' => [{ 'name' => 'user-group', 'type' => 'select', 'proxies' => ['user-node'] }],
              'rules' => ['MATCH,user-group'] }
    File.write(@config, YAML.dump(@base))
  end

  def teardown
    FileUtils.remove_entry(@dir)
  end

  def test_multiple_nodes_preserve_user_routing_and_have_no_credentials
    File.write(@selection, "a 11080\nb 11081\n")
    merge_managed(@config, @selection, @ports, @dir)
    result = YAML.safe_load(File.read(@config))
    assert_equal @base['proxy-groups'], result['proxy-groups']
    assert_equal @base['rules'], result['rules']
    assert_equal %w[user-node OpenKill-Naive-a OpenKill-Naive-b], result['proxies'].map { |p| p['name'] }
    assert_equal [11080, 11081], result['proxies'].last(2).map { |p| p['port'] }
    assert result['proxies'].last(2).all? { |p| p['server'] == '127.0.0.1' && p['udp'] == false }
  end

  def test_conflicts_and_malformed_selection_leave_config_unchanged
    ["a 11080\nb 11080\n", "../bad 11080\n", "a 65536\n"].each do |selection|
      File.write(@selection, selection)
      before = File.binread(@config)
      assert_raises(RuntimeError) { merge_managed(@config, @selection, @ports, @dir) }
      assert_equal before, File.binread(@config)
    end
    @base['proxy-groups'][0]['name'] = 'OpenKill-Naive-a'
    File.write(@config, YAML.dump(@base))
    File.write(@selection, "a 11080\n")
    before = File.binread(@config)
    assert_raises(RuntimeError) { merge_managed(@config, @selection, @ports, @dir) }
    assert_equal before, File.binread(@config)
  end

  def test_empty_or_missing_selection_does_not_change_config
    before = File.binread(@config)
    merge_managed(@config, @selection, @ports, @dir)
    File.write(@selection, '')
    merge_managed(@config, @selection, @ports, @dir)
    assert_equal before, File.binread(@config)
  end

  def test_missing_node_or_changed_mapping_does_not_change_config
    File.write(@selection, "a 11080\n")
    before = File.binread(@config)
    File.write(@ports, "a 11082\n")
    assert_raises(RuntimeError) { merge_managed(@config, @selection, @ports, @dir) }
    assert_equal before, File.binread(@config)
    File.write(@ports, "a 11080\nb 11080\n")
    assert_raises(RuntimeError) { merge_managed(@config, @selection, @ports, @dir) }
    assert_equal before, File.binread(@config)
    File.write(@ports, "a 11080\n")
    File.unlink(File.join(@dir, 'a.json'))
    assert_raises(RuntimeError) { merge_managed(@config, @selection, @ports, @dir) }
    assert_equal before, File.binread(@config)
  end
end

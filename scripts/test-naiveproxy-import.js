#!/usr/bin/env node
/* Browser-side contract for the independent, link-first import dialog. */
const fs = require('fs');
const vm = require('vm');

const template = fs.readFileSync('luci-app-openkill/luasrc/view/openkill/naive_compatibility.htm', 'utf8');
const start = template.indexOf('function shareFields(');
const end = template.indexOf('function fill(', start);
if (start < 0 || end < 0) throw new Error('standalone parser boundary not found');
const context = { URL, decodeURIComponent };
vm.runInNewContext(template.slice(start, end), context);

function parse(link) { return context.shareFields(link); }

let result = parse('naive+https://fixture-user:fixture-secret@example.test:37489?security=tls&type=tcp&headerType=none#Fixture');
if (result.name !== 'Fixture' || result.server !== 'example.test' || result.port !== '37489' ||
    result.username !== 'fixture-user' || result.password !== 'fixture-secret' || result.transport !== 'https' || result.warning) {
  throw new Error('unexpected HTTPS import result');
}
result = parse('naiveproxy://fixture-user:fixture-secret@[2001:db8::1]:443?security=tls&type=tcp&headerType=none#IPv6');
if (result.server !== '[2001:db8::1]' && result.server !== '2001:db8::1') throw new Error('IPv6 import was not preserved');
if (!parse('naive+https://fixture-user:fixture-secret@example.test:443?unknown=x#Fixture').warning.includes('unknown')) {
  throw new Error('unknown parameter was hidden');
}
try { parse('https://fixture-user:fixture-secret@example.test:443#Fixture'); throw new Error('unsupported scheme accepted'); } catch (error) {
  if (error.message === 'unsupported scheme accepted') throw error;
}
console.log('NAIVEPROXY_IMPORT_BEHAVIOR=PASS');

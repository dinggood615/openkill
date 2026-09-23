#!/usr/bin/env node
const fs = require('fs');
const vm = require('vm');

const template = fs.readFileSync('luci-app-openkill/luasrc/view/openkill/server_url.htm', 'utf8');
const start = template.indexOf('function parseUrl');
const end = template.indexOf('function parseSocks');
if (start < 0 || end < 0) throw new Error('Naive parser boundary not found');
const values = {};
vm.runInThisContext(template.slice(start, end));
globalThis.setFormValue = function setFixtureFormValue(_sid, field, value) {
  values[field] = String(value == null ? '' : value);
};

function parse(link) {
  Object.keys(values).forEach((key) => delete values[key]);
  naiveImportWarnings = [];
  if (!parseNaiveProxy(link, 'fixture')) throw new Error(`parse failed: ${link}`);
  return { values: { ...values }, warnings: [...naiveImportWarnings] };
}

let result = parse('naive+https://alice:secret@example.com:37489?security=tls&type=tcp&headerType=none#YT');
if (result.values.type !== 'naiveproxy' || result.values.server !== 'example.com' ||
    result.values.port !== '37489' || result.values.naive_username !== 'alice' ||
    result.values.naive_password !== 'secret' || result.values.naive_transport !== 'https' ||
    result.values.name !== 'YT' || result.warnings.length !== 0) {
  throw new Error(`unexpected TCP result: ${JSON.stringify(result)}`);
}

result = parse('naiveproxy://alice:secret@[2001:db8::1]:443?security=tls&type=quic&unknown=x');
if (result.values.server !== '2001:db8::1' || result.values.naive_transport !== 'quic' ||
    !result.warnings.some((item) => item.indexOf('unknown') >= 0)) {
  throw new Error(`unexpected IPv6 result: ${JSON.stringify(result)}`);
}

console.log('NAIVEPROXY_IMPORT_BEHAVIOR=PASS');

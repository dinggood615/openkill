# Phase 3E.2D2D-R2D canonical D2D test configuration

The D2D device semantic-validation run uses one checked-in configuration:
`scripts/fixtures/3e2-safe.yaml`.  It is a deterministic, direct-only
Mihomo input for the authorized `192.168.1.102` test target.  It is not a
user default, a production recommendation, a release-readiness proof, or a
packet-path test configuration, and it must not be installed on another
router.

## Provenance

The temporary R2A/R2C candidate bytes and their session hash
`e894c2f7918038080ca05baa1311c8d7336e2a1497ce3324b767238fe7c76b05` could
not be recovered from the repository, its history, or project-generated test
artifacts.  R2D therefore does not chase that byte hash.  The checked-in
fixture is a new canonical byte identity whose semantic contract is derived
from the existing Mihomo compatibility baseline, OpenKill UCI defaults, the
D2C DNS contract, and the frozen Mark ABI.

The current canonical identity is:

```text
CANONICAL_D2D_CONFIG_SOURCE=scripts/fixtures/3e2-safe.yaml
CANONICAL_D2D_CONFIG_SHA256=9cd8d91750758823776df9c982c1e15f0baa1a72baa1792fa2f82c0df4d24a6e
```

`BYTE_EQUIVALENCE_TO_R2A=UNKNOWN`; the semantic fields are equivalent to the
frozen R2A contract (`SEMANTIC_EQUIVALENCE_TO_R2A=PASS`).

## Contract

The file contains only the fields required to validate a real TUN topology:

- `mode: rule` with the sole rule `MATCH,DIRECT`; proxy and group lists are
  empty.
- TUN is enabled on `utun`, uses the `system` stack, and leaves both
  `auto-route` and `auto-redirect` disabled so OpenKill retains routing and
  firewall ownership.
- IPv4 and IPv6 are enabled.  Fake-IP DNS listens on `127.0.0.1:7874` and
  uses a reserved documentation address as its deterministic direct-only
  nameserver.
- The OpenKill-owned fields asserted alongside the file are mode-1 firewall
  and dnsmasq listener `:53`, dnsmasq upstream `127.0.0.1#7874`, and the
  frozen `0x162/0xffffffff`, table `354`, preference `1888` Mark ABI.  The
  firewall target is intentionally not encoded as an invented Mihomo YAML
  key.

The verifier also checks that the D2C ports stay separate: `53` is never
treated as equivalent to `7874`.

## Verification

Run the local structural and semantic check from the repository root:

```sh
python3 scripts/verify_3e2_safe_config.py
python3 scripts/test-3e2-safe-config.py
```

When an approved Mihomo binary is available, add `--mihomo <path>` and
`--require-mihomo` to the verifier.  The existing compatibility matrix uses
official v1.19.30 and latest binaries; no daemon is started by this fixture
test, and verification writes only to an isolated temporary directory.

The verifier rejects duplicate YAML keys, binary NULs, non-empty credential or
provider fields, external provider URLs, unexpected configuration keys, and
any deviation from the semantic contract.  The focused test reads the
canonical bytes ten times and requires one hash and one semantic summary.

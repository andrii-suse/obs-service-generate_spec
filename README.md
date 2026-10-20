# obs-service-generate_spec

**Umbrella RPM Spec Generator Source Service for Open Build Service (OBS)**

`obs-service-generate_spec` automatically inspects upstream repositories, detects packaging manifests (`go.mod`, `Cargo.toml`, `pyproject.toml`), vendors dependencies offline, and synthesizes an idiomatic RPM `.spec` file.

If a repository already contains a `.spec` file, the service acts as a transparent **no-op** and exits with code `0`.

---

## Features

- **No-Op Guard:** Skips execution automatically if `*.spec` or `_service:*:*.spec` is already present.
- **Dynamic Plugin Architecture (`generate_spec.d/`):** Manifest matching by priority (`<prio>-<manifest>`, e.g. `30-go.mod`).
- **Admin Masking:** Symlink any plugin in `/etc/obs/service/generate_spec.d/<name>` to `/dev/null` to disable it.
- **Integrated Offline Vendoring:** Language plugins create offline vendor archives (`vendor.tar.zst` / `vendor.tar.xz`) and align `%prep` and `%build` macros in lockstep.
- **Ecosystems Supported:**
  - **Go (`go.mod`):** Automatically extracts Go version, module URL, detects entrypoint (`main.go`, `cmd/*/main.go`, `examples/*/main.go`), vendors dependencies, auto-detects systemd unit services (`<pkg>.service`) and man pages, injecting appropriate `%service_*` scriptlets and standard SUSE/openSUSE Go packaging macros.

---

## Service Definition Parameters

In an OBS `_service` file:

```xml
<services>
  <service name="generate_spec">
    <param name="compression">zst</param>
    <param name="vendor">auto</param>
  </service>
</services>
```

| Parameter | Allowed Values | Default | Description |
| :--- | :--- | :--- | :--- |
| `name` | string | *auto* | Override the generated package name. |
| `version` | string | `@VERSION@` | Override the package version (or use `@VERSION@` with `obs-service-set_version`). |
| `compression` | `zst`, `xz`, `gz` | `zst` | Compression format for offline vendor archive. |
| `flavor` | string | *auto* | Force a specific generator (e.g. `go`, `rust`, `python`). |
| `vendor` | `auto`, `enable`, `disable` | `auto` | Whether to vendor dependencies offline. |
| `source-dir` | path | `.` | Root directory of unpacked sources. |

---

## Directory Structure

```
obs-service-generate_spec/
├── generate_spec               # Umbrella CLI dispatcher
├── generate_spec.service       # OBS XML service definition
├── generate_spec.d/            # Plugin directory
│   └── 30-go.mod -> ../plugins/go_generator.py
├── plugins/
│   └── go_generator.py         # Go module plugin
├── tests/
│   └── test_generate_spec.py   # Unit and integration test suite
├── obs-service-generate_spec.spec # RPM packaging specification
└── Makefile
```

---

## Running the Tests

```bash
python3 -m unittest discover tests -v
```

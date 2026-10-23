# Adoption Plan: `obs-service-generate_spec` in Open Build Service

## Executive Summary & Plan Feasibility Evaluation

This document outlines the architectural evaluation and three-phase rollout plan for integrating `obs-service-generate_spec` into the Open Build Service (OBS) ecosystem.

### Architectural Verdict on the Proposed Plan: **Solid and Viable, with Crucial Nuances**
The proposed three-phase trajectory—**Client-Only (Phase 1) ➔ Server-Side Service (Phase 2) ➔ Zero-Config Native Sync (Phase 3)**—is architecturally sound, realistic, and risk-minimized. It allows early packager adoption without requiring changes to OBS core infrastructure, followed by opt-in server deployment, and culminates in zero-configuration upstream packaging.

However, deep investigation of the `open-build-service` codebase reveals **fundamental constraints in OBS's `scmsync` implementation** that directly impact how Phase 1 and Phase 2 can be realized:
1. **`scmsync` Packages are Strictly Read-Only in OBS API:** If a package has `<scmsync>` defined in its metadata, the OBS API violently rejects direct file commits (`ScmsyncReadOnly` exception). A user **cannot** run `osc service localrun` and then `osc commit` the generated `.spec` file into an `scmsync` package.
2. **`obs_scm_bridge` Explicitly Forbids `_service` Files:** The OBS backend backend script `commitobsscm` immediately halts if the synced Git tree returns a `_service` file (`die("obs_scm_bridge must not return _service files")`).
3. **Execution Separation:** Server-side source service pipelines (`bs_service` / `bs_servicedispatch`) and `scmsync` updates (`obs_scm_bridge`) currently run on different backend execution paths.

This document details how to navigate these architectural boundaries at each phase.

---

## Technical Analysis of OBS Core & `scmsync`

To understand the feasibility of each phase, we analyzed the relevant subsystems in `open-build-service`:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                            Open Build Service Architecture                       │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   [ Developer Workstation ]                                                      │
│        │                                                                         │
│        ├─► osc commit / API PUT ──► [ OBS API / Rails ]                          │
│        │                               │                                         │
│        │                               ▼                                         │
│        │                    Check: package.scmsync?                              │
│        │                    YES ──► raise ScmsyncReadOnly (403 Forbidden)         │
│        │                    NO  ──► bs_srcserver -> addrev_runservice            │
│        │                                                │                        │
│        │                                                ▼                        │
│        │                                    [ Service Dispatcher ]               │
│        │                                    (bs_service / container)             │
│        │                                    Runs: _service pipeline              │
│        │                                                                         │
│   [ Upstream Git Webhook ]                                                       │
│        │                                                                         │
│        ▼                                                                         │
│   POST /source?cmd=triggerscmsync                                                │
│        │                                                                         │
│        ▼                                                                         │
│   bs_srcserver: runservice_obsscm                                                │
│        │                                                                         │
│        ▼                                                                         │
│   [ obs_scm_bridge ]                                                             │
│   - Git clone / submodule update                                                 │
│   - Creates _scmsync.obsinfo & *.obscpio                                         │
│   - Packs directories, preserves top-level files                                 │
│        │                                                                         │
│        ▼                                                                         │
│   BSSrcServer::Service::commitobsscm                                             │
│   - Asserts: No `_service` files returned!                                       │
│   - Commits pseudo-revision 'obsscm' via $addrev (skips normal runservice!)      │
│        │                                                                         │
│        ▼                                                                         │
│   [ bs_sched / bs_worker ]                                                       │
│   - Looks for *.spec / build recipes                                             │
│   - IF NO SPEC FOUND ──► State: "broken / unresolvable"                          │
│   - IF SPEC FOUND     ──► Dispatches build job to sandbox worker                 │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Key Subsystem Constraints Discovered

1. **`ScmsyncReadOnly` Enforcement (`src/api/app/models/package.rb`, lines 1171, 1229; `src/api/app/controllers/source_package_controller.rb`, line 197):**
   ```ruby
   def check_for_scmsynced_package_and_project(project:, package:)
     return unless package.try(:scmsync).present? || project.try(:scmsync).present?
     scmsync_url = project.try(:scmsync) || package.try(:scmsync)
     raise ScmsyncReadOnly, "Can not change files in SCM bridged packages and projects: #{scmsync_url}"
   end
   ```
   When a package is configured with `<scmsync>`, OBS views the remote Git repository as the sole authoritative source of truth. Users cannot upload or modify files in OBS.

2. **Backend Guard against SCM-injected Services (`src/backend/BSSrcServer/Service.pm`, line 145):**
   ```perl
   sub commitobsscm {
     my ($projid, $packid, $servicemark, $rev, $files) = @_;
     die("obs_scm_bridge must not return _service files\n") 
       if grep {$_ eq '_serviceerror' || /^_service[:_]/} keys %$files;
     ...
   ```
   OBS purposely prevents Git repositories from providing `_service` XML definitions. This security sandbox prevents arbitrary untrusted code execution on the source server.

3. **`commitobsscm` Bypasses Subsequent Source Services (`src/backend/BSSrcServer/Service.pm`, lines 165–180):**
   Standard package commits call `addrev_runservice`, which triggers downstream services defined in `_service` or `_project/_service`. In contrast, `commitobsscm` directly calls `$addrev->(..., $files)` and notifies repository servers. It does **not** invoke `BSSrcServer::Service::runservice`.

---

## Phase 1: Client-Only Service (`osc service localrun` & Git Workflows)

### Objective
Allow upstream developers and packagers to use `obs-service-generate_spec` immediately on their local machines without installing anything on the OBS backend server.

### The `scmsync` Investigation & Workflow Paths
Because an `scmsync` package is read-only in the OBS API, the user cannot run `osc service localrun` and push the spec to OBS with `osc commit`. Therefore, Phase 1 provides **two distinct operating models**:

```
                       PHASE 1 OPERATIONAL MODELS
                       
     ┌─────────────────────────────────────────────────────────────┐
     │ Model 1A: Git-Side Upstream Commit (True scmsync Workflow)  │
     ├─────────────────────────────────────────────────────────────┤
     │  Local Git Repo ──► Run `generate_spec --outdir .`          │
     │                 ──► Generates <name>.spec                   │
     │                 ──► git add *.spec && git push              │
     │                 ──► OBS scmsync clones repo (finds spec!)   │
     │                 ──► OBS Worker builds package               │
     └─────────────────────────────────────────────────────────────┘

     ┌─────────────────────────────────────────────────────────────┐
     │ Model 1B: Traditional OBS Package (No scmsync in Meta)      │
     ├─────────────────────────────────────────────────────────────┤
     │  OBS Package    ──► Define _service with mode="localonly"   │
     │                 ──► osc service localrun                    │
     │                 ──► obs_scm fetches code + generate_spec    │
     │                 ──► osc add *.spec && osc commit            │
     │                 ──► Spec stored in OBS backend              │
     └─────────────────────────────────────────────────────────────┘
```

#### Model 1A: Upstream Git-Side Generation (Recommended for `scmsync`)
In this model, the package in OBS is configured with `<scmsync>` pointing to upstream Git:
1. **Developer Workstation:**
   The developer clones the Git repository:
   ```bash
   git clone https://github.com/myorg/my-go-tool.git
   cd my-go-tool
   ```
2. **Local Generation:**
   The developer invokes `generate_spec` locally:
   ```bash
   obs-service-generate_spec --source-dir . --outdir .
   # Or using standalone binary:
   generate_spec --source-dir . --outdir .
   ```
   `generate_spec` identifies `go.mod`, resolves the version from Git tags, and emits `my-go-tool.spec` with:
   `# AUTO-GENERATED by obs-service-generate_spec`.
3. **Commit to Git:**
   ```bash
   git add my-go-tool.spec
   git commit -m "chore: add auto-generated RPM spec"
   git push origin main
   ```
4. **OBS Ingestion:**
   OBS receives the webhook or polls Git, executes `obs_scm_bridge`, checks out the repository, discovers `my-go-tool.spec` at the root, and dispatches the build job.
5. **Version Bump Lifecycle (Signature Guard):**
   When the upstream project releases a new version, running `generate_spec` again detects `# AUTO-GENERATED by obs-service-generate_spec`. The **Signature-Aware No-Op Guard** permits updating and overwriting the spec with the new version and dependencies. If a maintainer later manually edits the spec and removes the signature, `generate_spec` treats it as a human-crafted spec and exits `0` without overwriting.

#### Model 1B: Traditional Local OBS Service Workflow (No `scmsync`)
For developers who do not want the `.spec` file committed into their upstream Git repository:
1. In OBS, the package is created as a normal package (without `<scmsync>` in `_meta`).
2. The user defines a local `_service` file:
   ```xml
   <services>
     <service name="obs_scm" mode="manual">
       <param name="url">https://github.com/myorg/my-go-tool.git</param>
       <param name="scm">git</param>
       <param name="versionformat">@PARENT_TAG@</param>
     </service>
     <service name="tar" mode="manual" />
     <service name="recompress" mode="manual">
       <param name="compression">zst</param>
     </service>
     <service name="generate_spec" mode="localonly" />
   </services>
   ```
3. The developer runs:
   ```bash
   osc service manualrun
   osc service localrun
   ```
4. `obs_scm` clones the repository, `generate_spec` parses the source and emits `my-go-tool.spec`.
5. The developer commits the generated spec and tarball directly into OBS:
   ```bash
   osc add my-go-tool.spec *.tar.zst
   osc commit -m "Initial generated package"
   ```

### Deliverables for Phase 1
* Standalone CLI packaging for `obs-service-generate_spec` (RPM for openSUSE/Fedora, Homebrew, pip/PyPI).
* Developer documentation explaining Model 1A and Model 1B.
* GitHub Actions / GitLab CI workflow templates for auto-generating the spec on release.

---

## Phase 2: Server-Side Source Service (`_service` inside OBS)

### Objective
Deploy `obs-service-generate_spec` onto OBS server instances so that users can define a `_service` XML file, allowing OBS to generate the `.spec` file automatically on the server during source preparation.

### Operational Model

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      PHASE 2 SERVER-SIDE PIPELINE                               │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   Package '_service' file:                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │ <services>                                                              │   │
│   │   <service name="obs_scm">                                              │   │
│   │     <param name="url">https://github.com/myorg/my-go-tool.git</param>   │   │
│   │     <param name="scm">git</param>                                       │   │
│   │   </service>                                                            │   │
│   │   <service name="generate_spec" />                                      │   │
│   │   <service name="set_version" />                                        │   │
│   │ </services>                                                             │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                          │
│                                      ▼                                          │
│   OBS Source Server Dispatcher (bs_service / call-service-in-container)         │
│   1. /usr/lib/obs/service/obs_scm       ──► Clones Git repo into workspace      │
│   2. /usr/lib/obs/service/generate_spec ──► Inspects go.mod / Cargo.toml        │
│                                         ──► Creates vendor.tar.xz archive       │
│                                         ──► Emits <name>.spec into --outdir     │
│   3. /usr/lib/obs/service/set_version   ──► Updates version placeholder         │
│                                      │                                          │
│                                      ▼                                          │
│   OBS Storage Engine: Commits generated artifacts with `_service:*` prefix      │
│   OBS Worker (bs_worker): Expands service artifacts and builds RPM              │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Installation & Deployment on OBS Server
1. **RPM Packaging:**
   `obs-service-generate_spec` is packaged as an RPM using the provided `obs-service-generate_spec.spec`.
2. **Target Paths:**
   - Service executable: `/usr/lib/obs/service/generate_spec` (mode 0755)
   - Service definition: `/usr/lib/obs/service/generate_spec.service` (mode 0644)
   - Plugin directory: `/usr/lib/obs/service/generate_spec.d/`
   - Admin drop-in directory: `/etc/obs/service/generate_spec.d/`
3. **Execution Sandbox:**
   Because `generate_spec` and language plugins (like Go or Cargo vendoring) may download dependencies during the vendor stage, the service is declared in `bs_service` with network access permissions in `call-service-in-container`:
   ```bash
   */obs_scm|*/generate_spec)
     SCM_COMMAND=1
     WITH_NET="1"
     ;;
   ```

### Project-Level Service Template (`_project/_service`)
To spare users from having to write `_service` XML in every package, Phase 2 enables **Project-Level Service Inheritance**.

In OBS, a project can define `_project/_service`:
```xml
<services>
  <service name="obs_scm">
    <param name="scm">git</param>
    <param name="versionformat">@PARENT_TAG@</param>
  </service>
  <service name="generate_spec" />
  <service name="set_version" />
</services>
```
When an empty package in this project is created with only a Git URL parameter, OBS's `getprojectservices` automatically injects this pipeline.

### Architectural Note regarding `scmsync` in Phase 2
In Phase 2, this workflow operates via the **standard OBS source service framework (`obs_scm`)**, not the `<scmsync>` element. As established during our code analysis, `obs_scm_bridge` in OBS rejects `_service` files. Therefore, Phase 2 is the bridge that empowers server-side automated packaging using standard OBS services, paving the way for Phase 3.

---

## Phase 3: Zero-Config Upstream Sync (`scmsync` Only)

### Objective
Upstream developers specify **only** their repository URL in OBS:
```xml
<package name="my-go-tool" project="home:developer">
  <scmsync>https://github.com/myorg/my-go-tool#main</scmsync>
</package>
```
No `.spec` file exists upstream. No `_service` file exists in the package. OBS automatically clones the code, discovers the language manifest, vendors dependencies, generates the spec, and produces the build.

### Core OBS Code Integration

Our investigation revealed the exact entry point in OBS where this chain can be activated with surgical precision.

In `open-build-service/src/backend/BSSrcServer/Service.pm`, function `generate_obs_scm_bridge_service`:

#### Current Code (`src/backend/BSSrcServer/Service.pm`, lines 274–285):
```perl
sub generate_obs_scm_bridge_service {
  my ($data) = @_;
  die("bad obs_scm_bridge data\n") unless $data->{'name'} eq 'obs_scm_bridge' && $data->{'url'};
  my @params;
  push @params, { 'name' => 'url', '_content' => $data->{'url'} };
  push @params, { 'name' => 'projectmode', '_content' => '1' } if $data->{'projectmode'};
  push @params, { 'name' => 'projectscmsync', '_content' => $data->{'projectscmsync'} } if $data->{'projectscmsync'};
  my $services = { 
    'service' => [ { 'name' => 'obs_scm_bridge', 'param' => \@params } ],
  };
  return BSUtil::toxml($services, $BSXML::services);
}
```

#### Enhanced Code for Phase 3:
```perl
sub generate_obs_scm_bridge_service {
  my ($data) = @_;
  die("bad obs_scm_bridge data\n") unless $data->{'name'} eq 'obs_scm_bridge' && $data->{'url'};
  my @params;
  push @params, { 'name' => 'url', '_content' => $data->{'url'} };
  push @params, { 'name' => 'projectmode', '_content' => '1' } if $data->{'projectmode'};
  push @params, { 'name' => 'projectscmsync', '_content' => $data->{'projectscmsync'} } if $data->{'projectscmsync'};
  
  my @service_list = ( { 'name' => 'obs_scm_bridge', 'param' => \@params } );
  
  # Automatically append generate_spec to the scmsync execution pipeline
  # if enabled in BSConfig or installed on system
  if ($BSConfig::scmsync_auto_generate_spec || -x '/usr/lib/obs/service/generate_spec') {
    push @service_list, { 'name' => 'generate_spec' };
  }
  
  my $services = { 'service' => \@service_list };
  return BSUtil::toxml($services, $BSXML::services);
}
```

### End-to-End Execution Flow in Phase 3

```
1. SCM Event / Webhook Trigger
   │
   ▼
2. OBS receives POST /source?cmd=triggerscmsync
   │
   ▼
3. BSSrcServer::Service::runservice_obsscm calls doservicerpc with in-memory pipeline:
   ┌─────────────────────────────────────────────────────────┐
   │ Pipeline: [ obs_scm_bridge ] ──► [ generate_spec ]      │
   └─────────────────────────────────────────────────────────┘
   │
   ├─► Step A: obs_scm_bridge runs:
   │   - Clones Git repository.
   │   - Writes `_scmsync.obsinfo` containing commit hash and timestamp.
   │   - Downloads any registered assets.
   │   - Packs subdirectories into `<dir>.obscpio`.
   │   - Top-level files (`go.mod`, `Cargo.toml`, README) remain in workspace.
   │
   ├─► Step B: generate_spec runs:
   │   - Executes check_existing_spec().
   │     * IF custom *.spec exists in repo: Logs notice and exits 0 immediately.
   │     * IF no spec exists: Continues.
   │   - Resolves package version from `_scmsync.obsinfo` (Tier 2 in resolve_version).
   │   - Matches manifest via `generate_spec.d/` (e.g. `30-go.mod`).
   │   - Executes plugin: creates `vendor.tar.xz` and emits `<package_name>.spec`.
   │
   ▼
4. BSSrcServer::Service::commitobsscm
   - Commits all generated files (`_scmsync.obsinfo`, `*.obscpio`, `vendor.tar.xz`, `<name>.spec`)
     as a clean revision under the `obsscm` pseudo-revision.
   │
   ▼
5. Build Dispatcher (bs_sched / bs_worker)
   - Discovers `<name>.spec`.
   - Sends build job to worker sandbox.
   - RPM is compiled and published.
```

### Safety & Backwards Compatibility Guarantees in Phase 3
1. **Zero Impact on Existing Packaging:** If an upstream repository already includes a `.spec` file (e.g., maintained by distribution packagers), `generate_spec` triggers its **No-Op Guard** and exits cleanly with return code `0`.
2. **Administrative Override:** OBS administrators can disable specific generators by symlinking the plugin name in `/etc/obs/service/generate_spec.d/` to `/dev/null`, or disable the chain entirely via `BSConfig.pm`.
3. **No Database Schema Alterations:** The integration uses the existing `scmsync` SQLite/MySQL tables without requiring database migrations.

---

## Phase Comparison Matrix

| Attribute | Phase 1: Client-Only | Phase 2: Server `_service` | Phase 3: Zero-Config `scmsync` |
| :--- | :--- | :--- | :--- |
| **OBS Core Changes Required** | **None** | **None** (Only service package install) | **Minimal** (PR to `Service.pm`) |
| **User Configuration** | Run local CLI or CI | Write `_service` XML in package | **Zero** (Only provide Git URL) |
| **Location of `.spec`** | Upstream Git repo or local OBS commit | Generated dynamically in OBS server | Generated dynamically in OBS server |
| **`scmsync` Element Used?** | Yes (Model 1A) or No (Model 1B) | No (Uses standard `obs_scm`) | **Yes (Full native integration)** |
| **Maintenance Burden** | Upstream developer runs CLI | Packager maintains `_service` XML | **Fully automated** |
| **Multi-Ecosystem Support** | Go, Rust, Python | Go, Rust, Python | Go, Rust, Python |
| **Offline Vendoring Handling** | Generated locally | Generated by server service | Generated in `obsscm` pipeline |

---

## Implementation Roadmap & Action Items

```
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│     Phase 1      │ ────► │     Phase 2      │ ────► │     Phase 3      │
│  Client Service  │       │  Server _service │       │  Native scmsync  │
└──────────────────┘       └──────────────────┘       └──────────────────┘
       │                          │                          │
       ├─ Publish standalone CLI  ├─ Package RPM for OBS     ├─ PR to Service.pm
       ├─ GitHub Action template  ├─ Deploy to OBS test node ├─ SCM OIDC trigger
       └─ Multi-language plugins  └─ Project-level templates └─ Full rollout
```

### Milestone 1 (Completing Phase 1 Readiness)
- [x] Umbrella dispatcher implementation (`generate_spec`).
- [x] Go module generator (`plugins/go_generator.py`).
- [x] Signature-aware no-op guard and 5-tier version resolution.
- [ ] Implement Rust (`10-Cargo.toml`) and Python (`20-pyproject.toml`) generators.
- [ ] Provide sample GitHub Action and GitLab CI templates demonstrating Model 1A.

### Milestone 2 (Phase 2 Deployment)
- [ ] Build and submit `obs-service-generate_spec` package to `openSUSE:Tools` and `OBS:Server:Unstable`.
- [ ] Install on test OBS instance.
- [ ] Verify execution of `_service` pipelines using `obs_scm` + `generate_spec` + `set_version`.
- [ ] Document project-level service configuration (`_project/_service`).

### Milestone 3 (Phase 3 OBS Core PR)
- [ ] Create Pull Request in `open-build-service`: Extend `generate_obs_scm_bridge_service` in `src/backend/BSSrcServer/Service.pm`.
- [ ] Add integration test in `open-build-service/dist/t/osc/` verifying `scmsync` of a spec-less Go repository.
- [ ] Document the zero-touch upstream workflow in OBS official documentation.

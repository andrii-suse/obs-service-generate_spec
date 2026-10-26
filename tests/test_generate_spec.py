#!/usr/bin/env python3
"""
Unit and integration tests for obs-service-generate_spec
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parent.parent
if not (SERVICE_DIR / "generate_spec").is_file():
    REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
    SERVICE_DIR = REPO_ROOT / "obs-service-generate_spec"
else:
    REPO_ROOT = SERVICE_DIR.parent

GENERATE_SPEC_BIN = SERVICE_DIR / "generate_spec"
EXAMPLES_DIR = REPO_ROOT / "examples" if (REPO_ROOT / "examples").is_dir() else (SERVICE_DIR / "examples")


class TestGenerateSpec(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_root = Path(self.temp_dir.name)
        self.outdir = self.test_root / "out"
        self.outdir.mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_noop_guard_plain_spec(self):
        """Verifies that an existing .spec file causes an immediate clean exit 0."""
        source_dir = self.test_root / "src"
        source_dir.mkdir()
        (source_dir / "existing.spec").write_text("Name: test\n")

        res = subprocess.run(
            [str(GENERATE_SPEC_BIN), "--source-dir", str(source_dir), "--outdir", str(self.outdir)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("Existing spec file found", res.stdout)
        # Ensure no new spec was generated in outdir
        self.assertEqual(list(self.outdir.glob("*.spec")), [])

    def test_noop_guard_service_prefixed_spec(self):
        """Verifies that an existing _service:*:*.spec file causes clean exit 0."""
        source_dir = self.test_root / "src"
        source_dir.mkdir()
        (source_dir / "_service:obs_scm:existing.spec").write_text("Name: test\n")

        res = subprocess.run(
            [str(GENERATE_SPEC_BIN), "--source-dir", str(source_dir), "--outdir", str(self.outdir)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("Existing spec file found", res.stdout)
        self.assertEqual(list(self.outdir.glob("*.spec")), [])

    def test_croc_generation(self):
        """Verifies spec generation for croc."""
        croc_dir = EXAMPLES_DIR / "croc"
        if not croc_dir.is_dir():
            self.skipTest("examples/croc not available")

        # Copy existing vendor archive so vendor step passes without net
        source_dir = self.test_root / "croc_src"
        shutil.copytree(croc_dir, source_dir)
        vendor_src = EXAMPLES_DIR / "obsproj" / "croc" / "vendor.tar.xz"
        if vendor_src.is_file():
            shutil.copy2(vendor_src, source_dir / "vendor.tar.xz")

        res = subprocess.run(
            [
                str(GENERATE_SPEC_BIN),
                "--source-dir", str(source_dir),
                "--outdir", str(self.outdir),
                "--version", "10.1.1",
                "--compression", "xz",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, f"Error: {res.stderr}")
        self.assertIn("Matched generator 'go_generator.py'", res.stdout)

        spec_file = self.outdir / "croc.spec"
        self.assertTrue(spec_file.is_file())
        content = spec_file.read_text()
        self.assertIn("Name:           croc", content)
        self.assertIn("Version:        10.1.1", content)
        self.assertIn("License:        MIT", content)
        self.assertIn("URL:            https://github.com/schollz/croc", content)
        self.assertIn("Source1:        vendor.tar.xz", content)
        self.assertIn("BuildRequires:  golang-packaging", content)
        self.assertIn("BuildRequires:  golang(API) >= 1.27.0", content)
        self.assertIn("BuildRequires:  systemd-rpm-macros", content)
        self.assertIn("install -D -m 0644 croc.service %{buildroot}%{_unitdir}/%{name}.service", content)
        self.assertIn("%service_add_post %{name}.service", content)
        self.assertIn("%{_unitdir}/%{name}.service", content)
        self.assertIn("%{_mandir}/man1/%{name}.1*", content)
        self.assertIn("go build -mod=vendor -buildmode=pie", content)
        self.assertIn("%license LICENSE", content)

    def test_pocketbase_entrypoint_detection(self):
        """Verifies spec generation and entrypoint detection for pocketbase (examples/base)."""
        pb_dir = EXAMPLES_DIR / "pocketbase"
        if not pb_dir.is_dir():
            self.skipTest("examples/pocketbase not available")

        source_dir = self.test_root / "pb_src"
        shutil.copytree(pb_dir, source_dir)
        vendor_src = EXAMPLES_DIR / "obsproj" / "pocketbase" / "vendor.tar.zst"
        if vendor_src.is_file():
            shutil.copy2(vendor_src, source_dir / "vendor.tar.zst")

        res = subprocess.run(
            [
                str(GENERATE_SPEC_BIN),
                "--source-dir", str(source_dir),
                "--outdir", str(self.outdir),
                "--version", "0.40.5",
                "--compression", "zst",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, f"Error: {res.stderr}")

        spec_file = self.outdir / "pocketbase.spec"
        self.assertTrue(spec_file.is_file())
        content = spec_file.read_text()
        self.assertIn("Name:           pocketbase", content)
        self.assertIn("Version:        0.40.5", content)
        self.assertIn("URL:            https://github.com/pocketbase/pocketbase", content)
        # Entrypoint must target examples/base
        self.assertIn("go build -mod=vendor -buildmode=pie -o %{name} ./examples/base", content)
        self.assertIn("%license LICENSE.md", content)

    def test_fzf_generation(self):
        """Verifies spec generation for fzf."""
        fzf_dir = EXAMPLES_DIR / "fzf"
        if not fzf_dir.is_dir():
            self.skipTest("examples/fzf not available")

        source_dir = self.test_root / "fzf_src"
        shutil.copytree(fzf_dir, source_dir)
        vendor_src = EXAMPLES_DIR / "obsproj" / "fzf" / "vendor.tar.zst"
        if vendor_src.is_file():
            shutil.copy2(vendor_src, source_dir / "vendor.tar.zst")

        res = subprocess.run(
            [
                str(GENERATE_SPEC_BIN),
                "--source-dir", str(source_dir),
                "--outdir", str(self.outdir),
                "--version", "0.74.4",
                "--compression", "zst",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, f"Error: {res.stderr}")

        spec_file = self.outdir / "fzf.spec"
        self.assertTrue(spec_file.is_file())
        content = spec_file.read_text()
        self.assertIn("Name:           fzf", content)
        self.assertIn("Version:        0.74.4", content)
        self.assertIn("URL:            https://github.com/junegunn/fzf", content)
        self.assertIn("BuildRequires:  golang(API) >= 1.23.0", content)

    def test_auto_version_from_obsinfo(self):
        """Verifies version resolution from _scmsync.obsinfo."""
        source_dir = self.test_root / "src_obsinfo"
        source_dir.mkdir()
        (source_dir / "go.mod").write_text("module example.com/mytool\ngo 1.21\n")
        (source_dir / "_scmsync.obsinfo").write_text("name: mytool\nversion: 2.5.1\n")

        res = subprocess.run(
            [str(GENERATE_SPEC_BIN), "--source-dir", str(source_dir), "--outdir", str(self.outdir), "--vendor", "disable"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        spec = (self.outdir / "mytool.spec").read_text()
        self.assertIn("Version:        2.5.1", spec)

    def test_auto_version_from_archive_name(self):
        """Verifies version resolution from source archive filename."""
        source_dir = self.test_root / "src_archive"
        source_dir.mkdir()
        (source_dir / "go.mod").write_text("module example.com/archiveapp\ngo 1.21\n")
        (source_dir / "archiveapp-1.8.3.tar.gz").touch()

        res = subprocess.run(
            [str(GENERATE_SPEC_BIN), "--source-dir", str(source_dir), "--outdir", str(self.outdir), "--vendor", "disable"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        spec = (self.outdir / "archiveapp.spec").read_text()
        self.assertIn("Version:        1.8.3", spec)

    def test_auto_version_from_git_tag(self):
        """Verifies version resolution from git tag in pocketbase."""
        pb_dir = EXAMPLES_DIR / "pocketbase"
        if not pb_dir.is_dir():
            self.skipTest("examples/pocketbase not available")

        # Run without passing --version to test auto-detection
        res = subprocess.run(
            [str(GENERATE_SPEC_BIN), "--source-dir", str(pb_dir), "--outdir", str(self.outdir), "--vendor", "disable"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        spec = (self.outdir / "pocketbase.spec").read_text()
        self.assertIn("Version:        0.40.5", spec)

    def test_version_bump_regeneration(self):
        """Verifies that an existing spec with GENERATOR_SIGNATURE is regenerated on version bump."""
        source_dir = self.test_root / "src_bump"
        source_dir.mkdir()
        (source_dir / "go.mod").write_text("module example.com/bumpapp\ngo 1.21\n")

        # Run 1: generate initial v1.0.0
        res1 = subprocess.run(
            [str(GENERATE_SPEC_BIN), "--source-dir", str(source_dir), "--outdir", str(self.outdir), "--version", "1.0.0", "--vendor", "disable"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res1.returncode, 0)
        spec1 = (self.outdir / "bumpapp.spec").read_text()
        self.assertIn("Version:        1.0.0", spec1)
        changes1 = (self.outdir / "bumpapp.changes").read_text()
        self.assertIn("version 1.0.0", changes1)

        # Simulate version bump in OBS: copy generated spec and changes into package/source dir
        shutil.copy2(self.outdir / "bumpapp.spec", source_dir / "bumpapp.spec")
        shutil.copy2(self.outdir / "bumpapp.changes", source_dir / "bumpapp.changes")

        # Run 2: version bumped to v2.0.0
        res2 = subprocess.run(
            [str(GENERATE_SPEC_BIN), "--source-dir", str(source_dir), "--outdir", str(self.outdir), "--version", "2.0.0", "--vendor", "disable"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res2.returncode, 0)
        self.assertIn("Allowing update/regeneration", res2.stdout)

        spec2 = (self.outdir / "bumpapp.spec").read_text()
        self.assertIn("Version:        2.0.0", spec2)
        changes2 = (self.outdir / "bumpapp.changes").read_text()
        self.assertIn("Update to version 2.0.0", changes2)
        self.assertIn("version 1.0.0", changes2)

    def test_vendor_checksum_cache(self):
        """Verifies vendor archive SHA256 checksum creation and cache reuse."""
        source_dir = self.test_root / "src_cache"
        source_dir.mkdir()
        (source_dir / "go.mod").write_text("module example.com/cacheapp\ngo 1.21\n")
        # Create a dummy vendor archive
        (source_dir / "vendor.tar.xz").touch()

        res = subprocess.run(
            [str(GENERATE_SPEC_BIN), "--source-dir", str(source_dir), "--outdir", str(self.outdir), "--compression", "xz"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        sha_file = self.outdir / "vendor.tar.xz.sha256"
        self.assertTrue(sha_file.is_file())
        self.assertEqual(len(sha_file.read_text().strip()), 64)

    def test_masking_via_dev_null(self):
        """Verifies that symlinking a plugin to /dev/null masks it."""
        source_dir = self.test_root / "src"
        source_dir.mkdir()
        (source_dir / "go.mod").write_text("module example.com/masked\ngo 1.21\n")

        custom_plugin_dir = self.test_root / "plugins"
        custom_plugin_dir.mkdir()
        # Mask 30-go.mod
        (custom_plugin_dir / "30-go.mod").symlink_to("/dev/null")

        res = subprocess.run(
            [
                str(GENERATE_SPEC_BIN),
                "--source-dir", str(source_dir),
                "--outdir", str(self.outdir),
                "--plugin-dir", str(custom_plugin_dir),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertTrue(
            "No matching manifest found" in res.stdout or "all plugins masked" in res.stdout,
            f"Expected masked output, got: {res.stdout}",
        )
        self.assertEqual(list(self.outdir.glob("*.spec")), [])


if __name__ == "__main__":
    unittest.main()

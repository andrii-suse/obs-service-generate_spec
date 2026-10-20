#
# spec file for package obs-service-generate_spec
#
# Copyright (c) 2026 SUSE LLC
#
# All modifications and additions to the file contributed by third parties
# remain the property of their copyright owners, unless otherwise agreed
# upon. The license for this file, and modifications and additions to the
# file, is the same license as for the pristine package itself.
#

Name:           obs-service-generate_spec
Version:        0.1.0
Release:        0
Summary:        Umbrella RPM Spec Generator Source Service for Open Build Service
License:        GPL-2.0-or-later
Group:          Development/Tools/Building
URL:            https://github.com/openSUSE/obs-service-generate_spec
Source0:        %{name}-%{version}.tar.gz
BuildRequires:  python3-base >= 3.10
Requires:       python3-base >= 3.10
Requires:       tar
Suggests:       zstd
Suggests:       xz
BuildArch:      noarch

%description
An Open Build Service source service that detects upstream repository manifests
(such as go.mod, Cargo.toml, pyproject.toml) and automatically generates an
idiomatic RPM .spec file, vendoring dependencies offline when required.

%package go
Summary:        Go module plugin for obs-service-generate_spec
Requires:       %{name} = %{version}-%{release}
Requires:       go
Suggests:       zstd

%description go
Plugin for obs-service-generate_spec to automatically package Go applications
from repositories containing a go.mod file.

%prep
%autosetup -p1

%build
# Nothing to build (pure Python)

%install
install -d -m 0755 %{buildroot}%{_prefix}/lib/obs/service
install -d -m 0755 %{buildroot}%{_prefix}/lib/obs/service/generate_spec.d
install -d -m 0755 %{buildroot}%{_prefix}/lib/obs/service/plugins

install -m 0755 generate_spec %{buildroot}%{_prefix}/lib/obs/service/generate_spec
install -m 0644 generate_spec.service %{buildroot}%{_prefix}/lib/obs/service/generate_spec.service
install -m 0755 plugins/go_generator.py %{buildroot}%{_prefix}/lib/obs/service/plugins/go_generator.py
ln -sf ../plugins/go_generator.py %{buildroot}%{_prefix}/lib/obs/service/generate_spec.d/30-go.mod

%files
%dir %{_prefix}/lib/obs
%dir %{_prefix}/lib/obs/service
%dir %{_prefix}/lib/obs/service/generate_spec.d
%dir %{_prefix}/lib/obs/service/plugins
%{_prefix}/lib/obs/service/generate_spec
%{_prefix}/lib/obs/service/generate_spec.service

%files go
%{_prefix}/lib/obs/service/plugins/go_generator.py
%{_prefix}/lib/obs/service/generate_spec.d/30-go.mod

%changelog

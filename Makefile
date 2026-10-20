PREFIX ?= /usr
SERVICEDIR ?= $(PREFIX)/lib/obs/service
PLUGINDIR ?= $(SERVICEDIR)/generate_spec.d
PLUGINS_LIB ?= $(SERVICEDIR)/plugins

.PHONY: all test install clean

all:

test:
	python3 -m unittest discover tests -v

install:
	install -d -m 0755 $(DESTDIR)$(SERVICEDIR)
	install -d -m 0755 $(DESTDIR)$(PLUGINDIR)
	install -d -m 0755 $(DESTDIR)$(PLUGINS_LIB)
	install -m 0755 generate_spec $(DESTDIR)$(SERVICEDIR)/generate_spec
	install -m 0644 generate_spec.service $(DESTDIR)$(SERVICEDIR)/generate_spec.service
	install -m 0755 plugins/go_generator.py $(DESTDIR)$(PLUGINS_LIB)/go_generator.py
	ln -sf ../plugins/go_generator.py $(DESTDIR)$(PLUGINDIR)/30-go.mod

clean:
	rm -rf test_out .pytest_cache __pycache__ tests/__pycache__ plugins/__pycache__

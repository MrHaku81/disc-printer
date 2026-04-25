DOMAIN    = disc_printer
SRCDIR    = src/disc_printer
LOCALEDIR = $(SRCDIR)/locale
POTFILE   = $(LOCALEDIR)/$(DOMAIN).pot

# Alle Python-Quelldateien (ohne __pycache__)
PY_SRCS = $(shell find $(SRCDIR) -name "*.py" ! -path "*/__pycache__/*" | sort)

.PHONY: pot update-po init-po compile-mo clean-mo help

help:
	@echo "Verfügbare Ziele:"
	@echo "  make pot            — $(POTFILE) aus Quellcode neu erzeugen"
	@echo "  make update-po      — Alle .po-Dateien gegen .pot aktualisieren"
	@echo "  make init-po LANG=X — Neue Sprache X anlegen (z.B. LANG=en)"
	@echo "  make compile-mo     — .po → .mo kompilieren"
	@echo "  make clean-mo       — Alle .mo-Dateien entfernen"

# ── .pot erzeugen ─────────────────────────────────────────────────────────────
pot:
	xgettext \
		--language=Python \
		--keyword=_ \
		--keyword=ngettext:1,2 \
		--package-name=disc-printer \
		--package-version=$(shell grep '^version' pyproject.toml | head -1 | cut -d'"' -f2) \
		--msgid-bugs-address=haku81.kk@gmail.com \
		--copyright-holder="haku" \
		--from-code=UTF-8 \
		--add-comments=TRANSLATORS: \
		--sort-by-file \
		--output=$(POTFILE) \
		$(PY_SRCS)
	@echo "→ $(POTFILE) aktualisiert ($(shell grep -c '^msgid' $(POTFILE)) Einträge)"

# ── .po-Dateien aktualisieren ─────────────────────────────────────────────────
update-po: pot
	@for po in $(LOCALEDIR)/*/LC_MESSAGES/$(DOMAIN).po; do \
		echo "  Aktualisiere $$po …"; \
		msgmerge --update --backup=off --no-fuzzy-matching $$po $(POTFILE); \
	done

# ── Neue Sprache initialisieren ───────────────────────────────────────────────
init-po:
ifndef LANG
	$(error LANG ist nicht gesetzt — Aufruf: make init-po LANG=en)
endif
	mkdir -p $(LOCALEDIR)/$(LANG)/LC_MESSAGES
	msginit \
		--locale=$(LANG) \
		--input=$(POTFILE) \
		--output=$(LOCALEDIR)/$(LANG)/LC_MESSAGES/$(DOMAIN).po \
		--no-translator
	@echo "→ $(LOCALEDIR)/$(LANG)/LC_MESSAGES/$(DOMAIN).po angelegt"
	@echo "  Bitte in LINGUAS eintragen und übersetzen."

# ── .po → .mo kompilieren ────────────────────────────────────────────────────
compile-mo:
	@count=0; \
	for po in $(LOCALEDIR)/*/LC_MESSAGES/$(DOMAIN).po; do \
		mo=$${po%.po}.mo; \
		echo "  $$po → $$mo"; \
		msgfmt --check $$po -o $$mo && count=$$((count+1)); \
	done; \
	echo "→ $$count .mo-Datei(en) kompiliert"

# ── Aufräumen ─────────────────────────────────────────────────────────────────
clean-mo:
	@find $(LOCALEDIR) -name "*.mo" -delete -print | sed 's/^/  entfernt: /'

# Variables
# Derive version from Python package (__version__) only
VERSION := $(shell python -c "import eigenpuls; print(eigenpuls.__version__)" 2>/dev/null)
ifeq ($(strip $(VERSION)),)
  $(error VERSION is empty; ensure eigenpuls is importable and __version__ is set)
endif
ifeq ($(VERSION),0.0.0)
  $(error Invalid VERSION: 0.0.0; set a proper version or tag before running Make targets)
endif
# Compute NEXT_VERSION by bumping patch of VERSION (override if needed)
NEXT_VERSION ?= $(shell python -c "import eigenpuls,re; v=eigenpuls.__version__; m=re.match(r'^v?(\\d+)\\.(\\d+)\\.(\\d+)', v or '0.0.0'); maj,mi,pa = m.groups() if m else ('0','0','0'); print(f'{maj}.{mi}.{int(pa)+1}')" 2>/dev/null)
REGISTRY ?= docker.io
NAMESPACE ?= verlusti
IMAGE_NAME ?= eigenpuls
IMAGE ?= $(REGISTRY)/$(NAMESPACE)/$(IMAGE_NAME)
PYTHON ?= python
PIP ?= python -m pip

# Helper
TAG_LATEST ?= latest
VENV ?= 
# Strip leading 'v' from git tag for docker tags (v0.2.1 -> 0.2.1)
DOCKER_VERSION := $(patsubst v%,%,$(VERSION))

.PHONY: help
help:
	@echo "Targets:"
	@echo "  build           - Build python sdist/wheel"
	@echo "  publish         - Publish python package to PyPI (twine)"
	@echo "  tag             - Create and push git tag v$(VERSION) (uses Python __version__)"
	@echo "  tag-<ver>       - e.g., make tag-$(NEXT_VERSION) (shorthand for VERSION=<ver>)"
	@echo "  docker-build    - Build Docker image with :$(DOCKER_VERSION) and :latest"
	@echo "  docker-tag      - Tag local image to $(IMAGE):$(DOCKER_VERSION) and :latest"
	@echo "  docker-push     - Push $(IMAGE):$(DOCKER_VERSION) and :latest"
	@echo "  release         - Tag git, push tag, build & publish PyPI, build & push Docker"
	@echo "  release-<ver>   - e.g., make release-$(NEXT_VERSION) (shorthand for VERSION=<ver>)"
	@echo "  version         - Show current version (from Python __version__)"
	@echo "  version-source  - Show version and source (metadata|setuptools_scm)"

.PHONY: build
build:
	@echo "Building python package"
	export SETUPTOOLS_SCM_LOCAL_SCHEME=no-local-version && \
	rm -rf dist build *.egg-info && \
	$(PIP) install -U build twine && \
	$(PYTHON) -m build

.PHONY: publish
publish:
	@echo "Publishing python package"
	export SETUPTOOLS_SCM_LOCAL_SCHEME=no-local-version && \
	$(PYTHON) -m twine upload dist/*

.PHONY: tag
tag:
	@git tag -a v$(VERSION) -m "Release $(VERSION)"
	@git push origin v$(VERSION)

.PHONY: tag-push
tag-push:
	@git push origin v$(VERSION)

.PHONY: docker-build
docker-build:
	@echo "Building Docker image"
	docker build --build-arg EIGENPULS_VERSION=$(VERSION) -t $(IMAGE_NAME):$(DOCKER_VERSION) -t $(IMAGE_NAME):$(TAG_LATEST) .

.PHONY: docker-tag
docker-tag:
	@echo "Tagging Docker image to $(IMAGE)"
	docker tag $(IMAGE_NAME):$(DOCKER_VERSION) $(IMAGE):$(DOCKER_VERSION)
	docker tag $(IMAGE_NAME):$(TAG_LATEST) $(IMAGE):$(TAG_LATEST)

.PHONY: docker-push
docker-push:
	@echo "Pushing Docker image $(IMAGE)"
	docker push $(IMAGE):$(DOCKER_VERSION)
	docker push $(IMAGE):$(TAG_LATEST)


.PHONY: release
release: tag build publish docker-build docker-tag docker-push
	@echo "Release completed: $(VERSION)"

# Show current version
.PHONY: version
version:
	@python -c "import eigenpuls; print(eigenpuls.__version__)"

.PHONY: version-source
version-source:
	@python -c "import eigenpuls; print(eigenpuls.__version_source__)"

# Convenience pattern targets: make tag-0.2.1 / make release-0.2.1
.PHONY: tag-%
tag-%:
	@$(MAKE) tag VERSION=$*

.PHONY: release-%
release-%:
	@$(MAKE) release VERSION=$*

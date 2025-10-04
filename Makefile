# Variables
VERSION ?= 0.2.1
REGISTRY ?= docker.io
NAMESPACE ?= verlusti
IMAGE_NAME ?= eigenpuls
IMAGE ?= $(REGISTRY)/$(NAMESPACE)/$(IMAGE_NAME)
PYTHON ?= python
PIP ?= python -m pip

# Helper
TAG_LATEST ?= latest
VENV ?= 

.PHONY: help
help:
	@echo "Targets:"
	@echo "  build           - Build python sdist/wheel"
	@echo "  publish         - Publish python package to PyPI (twine)"
	@echo "  docker-build    - Build Docker image with :$(VERSION) and :latest"
	@echo "  docker-tag      - Tag local image to $(IMAGE):$(VERSION) and :latest"
	@echo "  docker-push     - Push $(IMAGE):$(VERSION) and :latest"
	@echo "  release         - Build python, docker, and push images"

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

.PHONY: docker-build
docker-build:
	@echo "Building Docker image"
	docker build -t $(IMAGE_NAME):$(VERSION) -t $(IMAGE_NAME):$(TAG_LATEST) .

.PHONY: docker-tag
docker-tag:
	@echo "Tagging Docker image to $(IMAGE)"
	docker tag $(IMAGE_NAME):$(VERSION) $(IMAGE):$(VERSION)
	docker tag $(IMAGE_NAME):$(TAG_LATEST) $(IMAGE):$(TAG_LATEST)

.PHONY: docker-push
docker-push:
	@echo "Pushing Docker image $(IMAGE)"
	docker push $(IMAGE):$(VERSION)
	docker push $(IMAGE):$(TAG_LATEST)

.PHONY: release
release: build docker-build docker-tag docker-push
	@echo "Release completed: $(VERSION)"

#!/bin/bash
export SETUPTOOLS_SCM_LOCAL_SCHEME=no-local-version
python -m twine upload dist/*

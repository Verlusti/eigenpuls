#!/bin/bash
export SETUPTOOLS_SCM_LOCAL_SCHEME=no-local-version
rm -rf dist build *.egg-info
python -m pip install -U build twine
python -m build

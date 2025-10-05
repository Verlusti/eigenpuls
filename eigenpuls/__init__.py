"""Package version resolution.

Strict rule:
1) If installed: read version from package metadata
2) Else (source tree): compute via setuptools_scm
3) If neither works: fail fast with a clear error
"""

__version__: str = "0.0.0"
__version_source__: str = "unknown"

try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("eigenpuls")
    __version_source__ = "metadata"

except Exception:

    try:
        from setuptools_scm import get_version as _get_version
        __version__ = _get_version(root="..", relative_to=__file__, local_scheme="no-local-version")
        __version_source__ = "setuptools_scm"

    except Exception as _e:

        __version__ = "0.0.0"
        __version_source__ = "unknown"
        raise RuntimeError(
            "Unable to determine eigenpuls version. Ensure the package is installed or setuptools_scm is available."
        ) from _e
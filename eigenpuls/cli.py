from __future__ import annotations

"""Client-side CLI for eigenpuls.

This CLI talks to a running eigenpuls server over HTTP and has zero
server-side dependencies. It is intended for client/automation usage.
"""

from .config import get_app_config

import shutil
import os
from typing import Optional
from pathlib import Path
import subprocess
import tempfile
import importlib.resources as pkg_resources

# External dependencies
import fire


CLIENT_APP_NAME = "eigenpuls-client"


class CLI:

    def __init__(self):
        """Eigenpuls client CLI entrypoint (client-side)."""
        pass


    def version(self) -> str:
        """Print installed eigenpuls package version."""
        try:
            from importlib.metadata import version
            return version("eigenpuls")
        except Exception:
            return "0+unknown"


    def list_known_types(self) -> None:
        """List known service types."""

        from .service import ServiceKnownType

        print("Known service types:")
        for t in ServiceKnownType:
            print(f"  - {t.value}")


    def service_list(self, url: Optional[str] = None, apikey: Optional[str] = None) -> None:
        """Fetch and print the service list from a running eigenpuls server."""

        from .client import EigenpulsClient
        cfg = get_app_config()
        base_url = url or f"http://{cfg.host}:{cfg.port}"
        client = EigenpulsClient(base_url=base_url, apikey=apikey)
        resp = client.list_services()
        print(resp.model_dump())

    
    def current_apikey(self, show: bool = False) -> None:
        """Show current API key (masked by default)."""

        cfg = get_app_config()
        key_obj = getattr(cfg, "apikey", None)
        try:
            key = key_obj.get_secret_value()  # type: ignore[attr-defined]
        except Exception:
            key = str(key_obj or "")
        if show:
            print(f"Current API key: {key}")
            return
        if not key:
            print("Current API key: (not set)")
            return
        masked = key if len(key) <= 6 else f"{key[:3]}***{key[-2:]}"
        print(f"Current API key: {masked}")


    def service_config(self, service: str, config: str, url: Optional[str] = None, apikey: Optional[str] = None) -> None:
        """POST a ServiceConfig JSON to a running server for the given service."""

        import json as _json
        from .client import EigenpulsClient
        from .service import ServiceConfig as _SvcCfg
        cfg = get_app_config()
        base_url = url or f"http://{cfg.host}:{cfg.port}"
        payload = _SvcCfg.model_validate(_json.loads(config))
        client = EigenpulsClient(base_url=base_url, apikey=apikey)
        resp = client.update_config(service, payload)
        print(resp.model_dump())


    def service_worker(self, service: str, worker: str, health: str, url: Optional[str] = None, apikey: Optional[str] = None) -> None:
        """POST a ServiceStatusHealth JSON to a running server for service/worker."""

        import json as _json
        from .client import EigenpulsClient
        from .service import ServiceStatusHealth as _Health
        cfg = get_app_config()
        base_url = url or f"http://{cfg.host}:{cfg.port}"
        payload = _Health.model_validate(_json.loads(health))
        client = EigenpulsClient(base_url=base_url, apikey=apikey)
        resp = client.update_worker(service, worker, payload)
        print(resp.model_dump())

    
    def client_app_name(self) -> str:
        """Print the name of the embedded client application."""

        return CLIENT_APP_NAME


    def probe_cmd(
        self,
        probe: str,
        service: str,
        worker: str,
        url: str,
        host: Optional[str] = None,
        port: Optional[int] = None,
        path: Optional[str] = None,
        apikey_env_var: str = "EIGENPULS_APIKEY",
        script_path: Optional[str] = None,
    ) -> str:
        """Factory: emit a one-liner bash command to run a probe and report.

        - probe: postgres|redis|rabbitmq|http|tcp
        - service/worker: identifiers reported to eigenpuls
        - url: eigenpuls base URL
        - host/port/path: probe target (path only for http)
        - apikey_env_var: environment variable name to read bearer token from
        - script_path: path to the client script (defaults to /opt/eigenpuls-client.sh)
        """

        probe = probe.lower().strip()
        allowed = {"postgres", "redis", "rabbitmq", "http", "tcp"}
        if probe not in allowed:
            raise ValueError(f"unsupported probe: {probe}")
        
        if not url:
            raise ValueError("url is required")

        base_url = url
        script_path = script_path or f"/opt/{self.client_script_name()}"
        envs = [
            "ACTION=probe",
            f"PROBE={probe}",
            f"SERVICE={service}",
            f"WORKER={worker}",
            f"EIGENPULS_URL={base_url}",
            f"EIGENPULS_APIKEY=${{{apikey_env_var}}}",
        ]
        if host:
            envs.append(f"PROBE_HOST={host}")
        if port is not None:
            envs.append(f"PROBE_PORT={port}")
        if probe == "http" and path:
            envs.append(f"PROBE_PATH={path}")
        env_str = " ".join(envs)
        # POSIX sh-compatible one-liner (no bash required)
        cmd = f"{env_str} sh {script_path}"

        return cmd

    def build_client_binary(self, output_path: Optional[str] = None) -> None:
        """Build the client binary."""
        
        from .__init__ import __pyinstaller_package__

        if not output_path:
            # determine by cwd and client app name
            output_path = os.path.join(os.getcwd(), self.client_app_name())
       
        if __pyinstaller_package__:
            print("Cannot build client binary: I am already a PyInstaller package")
            
            print("Copying myself to: ", output_path)
            shutil.copy(__file__, output_path)

            return
        
        else:
            if not shutil.which("docker"):
                raise RuntimeError("docker is required to build the client binary")

            # Extract packaged resources to a temporary directory
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                res_dir = tmp_path / "res"
                work_dir = tmp_path / "work"
                out_dir = work_dir / "dist"
                res_dir.mkdir(parents=True, exist_ok=True)
                work_dir.mkdir(parents=True, exist_ok=True)
                out_dir.mkdir(parents=True, exist_ok=True)

                # Copy resource files
                for name in [
                    "pyinstaller.manylinux.Dockerfile",
                    "eigenpuls-client.spec",
                    "build_client_binary.sh",
                ]:
                    with pkg_resources.files("eigenpuls.resources").joinpath(name).open("rb") as src, \
                         (res_dir / name).open("wb") as dst:
                        dst.write(src.read())

                # Use prebuilt manylinux-shared builder image (no local build)
                image_tag = "bashonly/manylinux-shared:manylinux2014-py311"
                try:
                    subprocess.run(["docker", "pull", image_tag], check=True)
                except Exception:
                    pass

                # Run container build using resource script inside container
                container_script = "/res/build_client_binary.sh"
                uid = os.getuid() if hasattr(os, "getuid") else 0
                gid = os.getgid() if hasattr(os, "getgid") else 0
                subprocess.run([
                    "docker", "run", "--rm",
                    "-v", f"{res_dir}:/res:ro",
                    "-v", f"{work_dir}:/work",
                    image_tag,
                    f"OUT_DIR=/work/dist SPEC_PATH=/res/eigenpuls-client.spec bash {container_script} && chown -R {uid}:{gid} /work"
                ], check=True)

                # Locate built artifact
                artifact = out_dir / CLIENT_APP_NAME
                if not artifact.exists():
                    # Fallback: search
                    matches = list(out_dir.rglob(CLIENT_APP_NAME))
                    artifact = matches[0] if matches else None  # type: ignore[assignment]
                if not artifact or not artifact.exists():  # type: ignore[truthy-bool]
                    raise RuntimeError("unable to locate built client artifact in output directory")

                shutil.copy(str(artifact), output_path)
                print(f"Built client binary -> {output_path}")


def main():
    os.environ["PAGER"] = "cat"
    fire.Fire(CLI)




from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .models import DEFAULT_MODEL


class WyomingPiperService:
    """Small process manager for the wyoming-piper server binary."""

    def __init__(
        self,
        uri: str = "tcp://127.0.0.1:10200",
        voice: str = DEFAULT_MODEL,
        data_dir: str | Path | None = None,
        wyoming_piper_bin: str | None = None,
        piper_bin: str | None = None,
    ) -> None:
        self.uri = uri
        self.voice = voice
        self.data_dir = Path(data_dir or os.environ.get("WYOMING_PIPER_DATA_DIR", "models/wyoming-piper"))
        self.wyoming_piper_bin = wyoming_piper_bin or os.environ.get("WYOMING_PIPER_BIN", "wyoming-piper")
        self.piper_bin = piper_bin or os.environ.get("PIPER_BIN")
        self.process: subprocess.Popen[bytes] | None = None

    def command(self) -> list[str]:
        executable = shutil.which(self.wyoming_piper_bin)
        if executable is None:
            raise RuntimeError(
                f"Wyoming Piper executable {self.wyoming_piper_bin!r} was not found."
            )

        command = [
            executable,
            "--uri",
            self.uri,
            "--voice",
            self.voice,
            "--data-dir",
            str(self.data_dir),
            "--download-dir",
            str(self.data_dir),
        ]
        if self.piper_bin:
            command.extend(["--piper", self.piper_bin])
        return command

    def start(self) -> subprocess.Popen[bytes]:
        if self.process and self.process.poll() is None:
            return self.process

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.process = subprocess.Popen(self.command())
        return self.process

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=10)

    def __enter__(self) -> WyomingPiperService:
        self.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.stop()

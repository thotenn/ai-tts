from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import tkinter as tk
import urllib.error
import urllib.request
from pathlib import Path
from tkinter import messagebox, ttk

from .models import DEFAULT_MODEL, MODELS


API_URL = "http://127.0.0.1:8000/speak"


class PiperGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Piper TTS Sandbox")
        self.geometry("620x360")
        self.current_player: subprocess.Popen[bytes] | None = None

        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.status_var = tk.StringVar(value="Listo")

        self._build_ui()

    def _build_ui(self) -> None:
        main = ttk.Frame(self, padding=16)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="Texto para sintetizar").pack(anchor="w")
        self.text = tk.Text(main, height=9, wrap="word")
        self.text.pack(fill="both", expand=True, pady=(6, 12))
        self.text.insert("1.0", "Hola, esta es una prueba de voz en espanhol latinoamericano con Piper.")
        self.text.bind("<Control-Return>", self._on_speak_event)
        self.text.bind("<Return>", self._on_speak_event)

        controls = ttk.Frame(main)
        controls.pack(fill="x")

        ttk.Label(controls, text="Modelo").pack(side="left")
        model_combo = ttk.Combobox(
            controls,
            textvariable=self.model_var,
            values=sorted(MODELS),
            state="readonly",
            width=24,
        )
        model_combo.pack(side="left", padx=(8, 12))

        self.button = ttk.Button(controls, text="Hablar", command=self.speak)
        self.button.pack(side="left")

        ttk.Label(main, textvariable=self.status_var).pack(anchor="w", pady=(12, 0))

    def _on_speak_event(self, _event: tk.Event[tk.Misc]) -> str:
        self.speak()
        return "break"

    def speak(self) -> None:
        text = self.text.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Texto vacio", "Escribe algo para sintetizar.")
            return

        self.button.configure(state="disabled")
        self.status_var.set("Generando audio...")
        threading.Thread(target=self._speak_worker, args=(text, self.model_var.get()), daemon=True).start()

    def _speak_worker(self, text: str, model: str) -> None:
        try:
            wav_path = self._request_audio(text, model)
            self._play_audio(wav_path)
            self.after(0, lambda: self.status_var.set(f"Reproduciendo con {model}"))
        except Exception as exc:  # noqa: BLE001 - GUI must surface any backend/player issue.
            self.after(0, lambda: messagebox.showerror("Error", str(exc)))
            self.after(0, lambda: self.status_var.set("Error"))
        finally:
            self.after(0, lambda: self.button.configure(state="normal"))

    def _request_audio(self, text: str, model: str) -> Path:
        payload = json.dumps({"text": text, "model": model}).encode("utf-8")
        request = urllib.request.Request(
            API_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                wav = response.read()
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "No pude conectar con la API. Ejecuta primero: python -m piper_sandbox.api"
            ) from exc

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        wav_path = Path(tmp.name)
        wav_path.write_bytes(wav)
        return wav_path

    def _play_audio(self, wav_path: Path) -> None:
        player = self._available_player()
        if player is None:
            raise RuntimeError("No encontre reproductor de audio. Instala paplay, aplay o ffplay.")

        if self.current_player and self.current_player.poll() is None:
            self.current_player.terminate()

        command = {
            "paplay": ["paplay", str(wav_path)],
            "aplay": ["aplay", str(wav_path)],
            "ffplay": ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(wav_path)],
        }[player]
        self.current_player = subprocess.Popen(command)

    def _available_player(self) -> str | None:
        from shutil import which

        for player in ("paplay", "aplay", "ffplay"):
            if which(player):
                return player
        return None


def main() -> None:
    PiperGui().mainloop()


if __name__ == "__main__":
    main()

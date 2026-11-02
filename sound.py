"""Optional Windows sounds. Importing this module never opens an audio device."""

import os

from inventory.config import PROJECT_ROOT


class SoundEffect:
    def __init__(self, filename):
        self.path = PROJECT_ROOT / "assets" / "sound" / filename

    def play(self, *, enabled=None):
        if enabled is None:
            enabled = os.getenv("INVENTORY_SOUND", "0").lower() in {"1", "true", "yes"}
        if not enabled or not self.path.is_file():
            return
        try:
            import winsound
            winsound.PlaySound(str(self.path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except (ImportError, RuntimeError, OSError):
            pass


error_sound = SoundEffect("error.wav")
click_btnsnd = SoundEffect("buttonclickrelease.wav")
warning_snd = SoundEffect("reminder.wav")
hover_snd = SoundEffect("buttonrollover.wav")
release_snd = SoundEffect("buttonclick.wav")
successful = SoundEffect("bell1.wav")
limit_output = SoundEffect("limitation.wav")
hover_lit = SoundEffect("lit.wav")
successful2 = SoundEffect("task_complete.wav")
nvg = SoundEffect("nvg_on.wav")
step_rec = SoundEffect("stepin_rectangle.wav")
signup_snd1 = SoundEffect("open_duck.wav")
signup_snd2 = SoundEffect("released_duck.wav")
one, two, three, four, five = (SoundEffect(f"number/{index}.wav") for index in range(1, 6))

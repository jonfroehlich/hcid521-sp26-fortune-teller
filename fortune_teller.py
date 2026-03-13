"""
Fortune Teller — Sound playback + thermal printer interactive station.

Keys A, S, D, F, H play sound files. Hold G for a synth tone.
Keys 1–4 print images (cat, eye, snake, sun) to a PM290C thermal printer.
Key 5 prints "Prototyping Studio!" as text.

Print jobs run in a background thread so the UI stays responsive.

Requirements:
    pip install pygame numpy bleak Pillow

Usage:
    python fortune_teller.py
"""

import asyncio
import math
import sys
import threading

import numpy as np
import pygame

import pm290c_printer

# ========== WINDOW ==========
WINDOW_WIDTH = 600
WINDOW_HEIGHT = 500
BACKGROUND_COLOR = (30, 30, 30)
FPS = 60

# ========== AUDIO ==========
SAMPLE_RATE = 44100
SYNTH_FREQUENCY = 523.25  # C5
SYNTH_AMPLITUDE = 0.3
SYNTH_DURATION_SEC = 5.0

SOUND_FILE_MAP = {
    pygame.K_a: ("sounds/tarot_wall.mp3", "Tarot wall"),
    pygame.K_s: ("sounds/chaotic_wall.mp3", "Chaotic wall"),
    pygame.K_d: ("sounds/randomnizer.mp3", "Randomnizer"),
    pygame.K_f: ("sounds/under_bridge.mp3", "Under bridge"),
    pygame.K_h: ("sounds/winning.mp3", "Winning"),
}

SYNTH_KEY = pygame.K_g
SYNTH_LABEL = "Synth tone"

# ========== PRINT ==========
PRINT_IMAGE_MAP = {
    pygame.K_1: ("images/cat.png", "Cat"),
    pygame.K_2: ("images/eye.png", "Eye"),
    pygame.K_3: ("images/snake.png", "Snake"),
    pygame.K_4: ("images/sun.png", "Sun"),
}

PRINT_TEXT_KEY = pygame.K_5
PRINT_TEXT_LABEL = "\"Prototyping Studio!\""
PRINT_TEXT_STRING = "Prototyping Studio!"
PRINT_TEXT_FONT_SIZE = 48

# ========== DISPLAY ORDER ==========
SOUND_KEY_DISPLAY = [
    (pygame.K_a, "A"),
    (pygame.K_s, "S"),
    (pygame.K_d, "D"),
    (pygame.K_f, "F"),
    (pygame.K_g, "G"),
    (pygame.K_h, "H"),
]

PRINT_KEY_DISPLAY = [
    (pygame.K_1, "1"),
    (pygame.K_2, "2"),
    (pygame.K_3, "3"),
    (pygame.K_4, "4"),
    (pygame.K_5, "5"),
]


# ========== AUDIO HELPERS ==========

def generate_sine_wave(frequency, duration_sec, sample_rate=SAMPLE_RATE,
                       amplitude=SYNTH_AMPLITUDE):
    """Generate a stereo sine wave as a pygame Sound object."""
    num_samples = int(sample_rate * duration_sec)
    t = np.arange(num_samples, dtype=np.float64) / sample_rate
    wave = amplitude * np.sin(2.0 * math.pi * frequency * t)
    samples_16 = (wave * 32767).astype(np.int16)
    stereo = np.column_stack((samples_16, samples_16))
    return pygame.sndarray.make_sound(stereo)


def load_sounds():
    """Load sound files and generate the synth tone.

    Returns:
        Dict mapping pygame key constants to Sound objects (or None on failure).
    """
    sounds = {}
    for key, (filepath, label) in SOUND_FILE_MAP.items():
        try:
            sounds[key] = pygame.mixer.Sound(filepath)
        except (FileNotFoundError, pygame.error) as err:
            print(f"Warning: Could not load '{filepath}': {err}")
            sounds[key] = None

    sounds[SYNTH_KEY] = generate_sine_wave(SYNTH_FREQUENCY, SYNTH_DURATION_SEC)
    return sounds


# ========== PRINT HELPERS ==========

class PrintManager:
    """Manages background print jobs so the pygame loop doesn't block.

    Only one print job runs at a time. Additional requests while a job
    is active are ignored with a console warning.
    """

    def __init__(self):
        self._busy = False
        self._status = "Ready"
        self._lock = threading.Lock()

    @property
    def status(self):
        """Current status string for UI display."""
        with self._lock:
            return self._status

    @property
    def busy(self):
        """Whether a print job is currently running."""
        with self._lock:
            return self._busy

    def request_image(self, image_path, label):
        """Request a background image print job.

        Args:
            image_path: Path to the image file.
            label: Display name for status messages.
        """
        if not self._try_start(f"Printing {label}..."):
            return
        thread = threading.Thread(
            target=self._run_async, args=(pm290c_printer.print_image, image_path),
            daemon=True,
        )
        thread.start()

    def request_text(self, text, font_size=PRINT_TEXT_FONT_SIZE):
        """Request a background text print job.

        Args:
            text: The text string to print.
            font_size: Font size in pixels.
        """
        if not self._try_start(f"Printing text..."):
            return
        thread = threading.Thread(
            target=self._run_async,
            args=(pm290c_printer.print_text, text),
            kwargs={"font_size": font_size},
            daemon=True,
        )
        thread.start()

    def _try_start(self, status_msg):
        """Attempt to claim the busy lock. Returns True if acquired."""
        with self._lock:
            if self._busy:
                print("Print job already in progress, ignoring request.")
                return False
            self._busy = True
            self._status = status_msg
        return True

    def _run_async(self, coro_func, *args, **kwargs):
        """Run an async print function in a new event loop, then release the lock."""
        try:
            asyncio.run(coro_func(*args, **kwargs))
            with self._lock:
                self._status = "Print complete!"
        except Exception as err:
            print(f"Print error: {err}")
            with self._lock:
                self._status = f"Error: {err}"
        finally:
            with self._lock:
                self._busy = False


# ========== RENDERING ==========

def _draw_centered_text(surface, font, text, x, y, color):
    """Render text centered at (x, y)."""
    rendered = font.render(text, True, color)
    rect = rendered.get_rect(center=(x, y))
    surface.blit(rendered, rect)


def render_ui(screen, fonts, print_manager):
    """Draw the full UI: sound keys, print keys, and printer status.

    Args:
        screen: The pygame display surface.
        fonts: Dict with 'large', 'medium', 'small' Font instances.
        print_manager: The PrintManager instance for status display.
    """
    screen.fill(BACKGROUND_COLOR)
    cx = WINDOW_WIDTH // 2

    # Title
    _draw_centered_text(screen, fonts["large"], "Fortune Teller",
                        cx, 40, (255, 255, 255))

    # ---- Sound section ----
    _draw_centered_text(screen, fonts["medium"], "-- Sounds --",
                        cx, 85, (180, 180, 255))

    y = 115
    for key, key_label in SOUND_KEY_DISPLAY:
        if key in SOUND_FILE_MAP:
            _, sound_label = SOUND_FILE_MAP[key]
        elif key == SYNTH_KEY:
            sound_label = SYNTH_LABEL
        else:
            continue
        _draw_centered_text(screen, fonts["small"], f"Key {key_label}: {sound_label}",
                            cx, y, (200, 200, 200))
        y += 25

    # ---- Print section ----
    _draw_centered_text(screen, fonts["medium"], "-- Thermal Printer --",
                        cx, y + 20, (255, 200, 150))

    y += 50
    for key, key_label in PRINT_KEY_DISPLAY:
        if key in PRINT_IMAGE_MAP:
            _, print_label = PRINT_IMAGE_MAP[key]
        elif key == PRINT_TEXT_KEY:
            print_label = PRINT_TEXT_LABEL
        else:
            continue
        _draw_centered_text(screen, fonts["small"], f"Key {key_label}: Print {print_label}",
                            cx, y, (200, 200, 200))
        y += 25

    # ---- Printer status ----
    status = print_manager.status
    if print_manager.busy:
        color = (255, 220, 100)
    elif "Error" in status:
        color = (255, 100, 100)
    elif "complete" in status.lower():
        color = (100, 255, 100)
    else:
        color = (150, 150, 150)

    _draw_centered_text(screen, fonts["small"], f"Printer: {status}",
                        cx, WINDOW_HEIGHT - 30, color)


# ========== MAIN LOOP ==========

def main():
    """Initialize pygame and run the main event/render loop."""
    pygame.init()
    pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=2)

    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Fortune Teller")
    clock = pygame.time.Clock()

    fonts = {
        "large": pygame.font.SysFont(None, 40),
        "medium": pygame.font.SysFont(None, 30),
        "small": pygame.font.SysFont(None, 26),
    }

    sounds = load_sounds()
    synth_playing = False
    print_manager = PrintManager()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                # ---- Sound keys ----
                if event.key in sounds and sounds[event.key] is not None:
                    if event.key == SYNTH_KEY:
                        if not synth_playing:
                            sounds[SYNTH_KEY].play(loops=-1)
                            synth_playing = True
                    else:
                        sounds[event.key].stop()
                        sounds[event.key].play()

                # ---- Print keys ----
                elif event.key in PRINT_IMAGE_MAP:
                    filepath, label = PRINT_IMAGE_MAP[event.key]
                    print_manager.request_image(filepath, label)

                elif event.key == PRINT_TEXT_KEY:
                    print_manager.request_text(PRINT_TEXT_STRING,
                                               font_size=PRINT_TEXT_FONT_SIZE)

            elif event.type == pygame.KEYUP:
                if event.key == SYNTH_KEY and synth_playing:
                    sounds[SYNTH_KEY].fadeout(100)
                    synth_playing = False

        render_ui(screen, fonts, print_manager)
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()

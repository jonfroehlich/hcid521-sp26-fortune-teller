"""
Sound Player — Keyboard-triggered sound playback.

Converted from a P5.js sketch. Press A, S, D, F to play sound files,
and hold G to play a sine wave oscillator.

Requirements:
    pip install pygame numpy

Usage:
    Place sound files in a 'sounds/' directory relative to this script,
    then run: python sound_player.py
"""

import sys
import math

import numpy as np
import pygame

# ========== CONSTANTS ==========
WINDOW_WIDTH = 600
WINDOW_HEIGHT = 400
BACKGROUND_COLOR = (30, 30, 30)
FPS = 60

# Audio settings
SAMPLE_RATE = 44100
SYNTH_FREQUENCY = 523.25  # C5
SYNTH_AMPLITUDE = 0.3
SYNTH_DURATION_SEC = 5.0  # Length of the generated sine buffer

# Key-to-sound-file mappings (key: (filename, display label))
SOUND_FILE_MAP = {
    pygame.K_a: ("sounds/tarot_wall.mp3", "Tarot wall"),
    pygame.K_s: ("sounds/chaotic_wall.mp3", "Chaotic wall"),
    pygame.K_d: ("sounds/randomnizer.mp3", "Randomnizer"),
    pygame.K_f: ("sounds/under_bridge.mp3", "Under bridge"),
    pygame.K_h: ("sounds/winning.mp3", "Winning"),
}

SYNTH_KEY = pygame.K_g
SYNTH_LABEL = "Synth tone"

# Display order for the UI
KEY_DISPLAY_ORDER = [
    (pygame.K_a, "A"),
    (pygame.K_s, "S"),
    (pygame.K_d, "D"),
    (pygame.K_f, "F"),
    (pygame.K_g, "G"),
    (pygame.K_h, "H"),
]


# ========== AUDIO HELPERS ==========

def generate_sine_wave(frequency, duration_sec, sample_rate=SAMPLE_RATE,
                       amplitude=SYNTH_AMPLITUDE):
    """Generate a stereo sine wave as a pygame Sound object.

    Args:
        frequency: Frequency in Hz.
        duration_sec: Duration of the buffer in seconds.
        sample_rate: Audio sample rate.
        amplitude: Peak amplitude in [0, 1].

    Returns:
        A pygame.mixer.Sound containing the sine wave.
    """
    num_samples = int(sample_rate * duration_sec)
    t = np.arange(num_samples, dtype=np.float64) / sample_rate
    wave = amplitude * np.sin(2.0 * math.pi * frequency * t)

    # Convert to 16-bit signed integers, then stack for stereo
    samples_16 = (wave * 32767).astype(np.int16)
    stereo = np.column_stack((samples_16, samples_16))

    return pygame.sndarray.make_sound(stereo)


def load_sounds():
    """Load all sound files and generate the synth tone.

    Returns:
        A dict mapping pygame key constants to pygame.mixer.Sound objects,
        or None for entries whose files could not be loaded.
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


# ========== RENDERING ==========

def render_ui(screen, font_large, font_medium, font_small):
    """Draw the instructions and key mappings.

    Args:
        screen: The pygame display surface.
        font_large: Font for the main instruction line.
        font_medium: Font for key mapping labels.
        font_small: Font for the hint line.
    """
    screen.fill(BACKGROUND_COLOR)
    cx = WINDOW_WIDTH // 2
    cy = WINDOW_HEIGHT // 2

    # Main instruction
    _draw_centered_text(screen, font_large, "Press A, S, D, F, or G to play sounds",
                        cx, cy - 80, (255, 255, 255))

    # Hint
    _draw_centered_text(screen, font_small, "(Click the window first if sounds don't play)",
                        cx, cy - 55, (150, 150, 150))

    # Key mappings
    y_offset = -20
    for key, key_label in KEY_DISPLAY_ORDER:
        if key in SOUND_FILE_MAP:
            _, sound_label = SOUND_FILE_MAP[key]
        elif key == SYNTH_KEY:
            sound_label = SYNTH_LABEL
        else:
            continue

        _draw_centered_text(screen, font_medium, f"Key {key_label}: {sound_label}",
                            cx, cy + y_offset, (200, 200, 200))
        y_offset += 25


def _draw_centered_text(surface, font, text, x, y, color):
    """Render text centered at (x, y).

    Args:
        surface: Target pygame surface.
        font: A pygame.font.Font instance.
        text: The string to render.
        x: Horizontal center position.
        y: Vertical center position.
        color: RGB tuple.
    """
    rendered = font.render(text, True, color)
    rect = rendered.get_rect(center=(x, y))
    surface.blit(rendered, rect)


# ========== MAIN LOOP ==========

def main():
    """Initialize pygame and run the main event loop."""
    pygame.init()
    pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=2)

    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Sound Player")
    clock = pygame.time.Clock()

    font_large = pygame.font.SysFont(None, 32)
    font_medium = pygame.font.SysFont(None, 28)
    font_small = pygame.font.SysFont(None, 24)

    sounds = load_sounds()
    synth_playing = False

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                sound = sounds.get(event.key)
                if sound is None:
                    continue

                if event.key == SYNTH_KEY:
                    # Hold-to-play: start the synth tone
                    if not synth_playing:
                        sound.play(loops=-1)
                        synth_playing = True
                else:
                    # Restart the sound file from the beginning
                    sound.stop()
                    sound.play()

            elif event.type == pygame.KEYUP:
                if event.key == SYNTH_KEY and synth_playing:
                    sounds[SYNTH_KEY].fadeout(100)  # ~100 ms fade out
                    synth_playing = False

        render_ui(screen, font_large, font_medium, font_small)
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()

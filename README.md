# Fortune Teller

Interactive sound + thermal printer station. Play sounds with keyboard keys and print fortunes (images or text) to a PM290C thermal printer over BLE.

## Controls

### Sounds (keys A–H)

| Key | Sound |
|-----|-------|
| A   | Tarot wall |
| S   | Chaotic wall |
| D   | Randomnizer |
| F   | Under bridge |
| G   | Synth tone (hold to play) |
| H   | Winning |

### Thermal Printer (keys 1–5)

| Key | Action |
|-----|--------|
| 1   | Print `images/cat.png` |
| 2   | Print `images/eye.png` |
| 3   | Print `images/snake.png` |
| 4   | Print `images/sun.png` |
| 5   | Print "Prototyping Studio!" text |

The printer status is shown at the bottom of the window. Only one print job runs at a time.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

> **Note:** This project uses `pygame-ce` (community edition) for Python 3.14 compatibility.

## Usage

```bash
python fortune_teller.py
```

To run just the sound player without printer features:

```bash
python sound_player.py
```

To print directly from the command line:

```bash
python pm290c_printer.py "Hello World!"
python pm290c_printer.py --image images/cat.png
python pm290c_printer.py --font-size 48 "Big Text"
```

## Project Structure

```
.
├── README.md
├── requirements.txt
├── fortune_teller.py        # Main app (sounds + printing)
├── sound_player.py          # Sound-only app
├── pm290c_printer.py        # Printer library + CLI
├── sounds/
│   ├── chaotic_wall.mp3
│   ├── randomnizer.mp3
│   ├── tarot_wall.mp3
│   ├── under_bridge.mp3
│   └── winning.mp3
└── images/
    ├── cat.png
    ├── eye.png
    ├── snake.png
    └── sun.png
```

## Adding Sounds or Print Images

Edit the dictionaries at the top of `fortune_teller.py`:

```python
# Add a sound
SOUND_FILE_MAP = {
    ...
    pygame.K_h: ("sounds/new_sound.mp3", "New sound"),
}

# Add a print image
PRINT_IMAGE_MAP = {
    ...
    pygame.K_6: ("images/moon.png", "Moon"),
}
```

Then add the key to the corresponding `_DISPLAY` list for it to appear in the UI.

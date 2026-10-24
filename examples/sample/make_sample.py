"""Build the synthetic sample video: fictional content, slides drawn with Pillow, voice from macOS `say`.

    uv run python examples/sample/make_sample.py          # writes examples/sample/sample.mp4

Everything in the video is invented ("Zorbex Beacon", "Lumen 40"); no third-party footage is involved.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
SIZE = (720, 1280)
FONTS = ["/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]

# (spoken text, slide title, slide lines). The last line of the table slide shows a number that is only on screen.
SCENES = [
    ("Does the Zorbex Beacon signal really predict the next move? I tested it on the fictional Lumen 40 index.",
     "ZORBEX BEACON TEST", ["Fictional signal", "Fictional index: LUMEN 40"]),
    ("For every session I also drew a random coin flip at the same time, and compared the two across 500 simulated runs.",
     "METHOD", ["Beacon vs random coin flip", "500 simulated runs"]),
    ("The beacon was right in 54.2 percent of sessions. The coin flip was right in 50.4 percent. A small edge of 3.8 points.",
     "HIT RATE", ["Beacon: 54.2%", "Coin flip: 50.4%", "Edge: 3.8 points"]),
    ("When the market opened above the beacon, it was right in 58 percent of cases, against 49.6 percent for the coin flip.",
     "OPEN ABOVE BEACON", ["Beacon: 58%", "Coin flip: 49.6%"]),
    ("Then I traded the signal. 812 trades over five years, plus 7.4 R before costs. After costs, most of the edge disappeared.",
     "TRADED RESULT", ["812 trades, 5 years", "Before costs: +7.4R", "Cost per trade: 0.04R"]),
    ("So the beacon has a small effect, but not enough to be profitable after costs.",
     "CONCLUSION", ["Small effect", "Not profitable after costs"]),
]


def font(size):
    for path in FONTS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def slide(path, title, lines):
    image = Image.new("RGB", SIZE, (18, 24, 38))
    draw = ImageDraw.Draw(image)
    draw.text((40, 160), title, font=font(60), fill=(255, 214, 102))
    for index, line in enumerate(lines):
        draw.text((40, 420 + index * 150), line, font=font(64), fill=(240, 240, 240))
    image.save(path)


def run(*args):
    subprocess.run([str(a) for a in args], check=True, capture_output=True)


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    )  # fmt: skip
    return float(out.stdout)


def main(target=HERE / "sample.mp4"):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        listing = []
        for index, (speech, title, lines) in enumerate(SCENES):
            audio, image, clip = tmp / f"a{index}.wav", tmp / f"s{index}.png", tmp / f"c{index}.mp4"
            run("say", "-v", "Samantha", "-r", "165", "-o", tmp / f"a{index}.aiff", speech)
            run("ffmpeg", "-v", "error", "-y", "-i", tmp / f"a{index}.aiff", "-ar", "16000", "-ac", "1", audio)
            slide(image, title, lines)
            seconds = duration(audio) + 0.6  # a short pause between scenes
            run("ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", "10", "-t", f"{seconds:.3f}", "-i", image,
                "-i", audio, "-af", "apad", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", clip)  # fmt: skip
            listing.append(f"file '{clip}'")
        (tmp / "list.txt").write_text("\n".join(listing))
        run("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", tmp / "list.txt", "-c", "copy", target)
    print(target, f"{duration(target):.1f}s")


if __name__ == "__main__":
    sys.exit(main())

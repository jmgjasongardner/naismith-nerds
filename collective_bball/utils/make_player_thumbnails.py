from pathlib import Path
from PIL import Image

# Adjust these to match your actual paths
# Example assumes:
#   naismith_nerds/
#     flask_app/
#       static/
#         player_pics/         <-- full-size PNGs live here
#         player_pics_thumbs/  <-- we'll create this for WebP thumbs
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE_DIR = PROJECT_ROOT / "static" / "player_pics"
THUMB_DIR = PROJECT_ROOT / "static" / "player_pics_thumbs"

# Thumbnail settings
THUMB_SIZE = (40, 40)  # this matches your 30x30 display with a bit of buffer
WEBP_QUALITY = 80  # 0–100; 80 is a good balance


def make_thumbnail(src_path: Path, dst_dir: Path) -> None:
    """Create a WebP thumbnail for a single image."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst_path = dst_dir / f"{src_path.stem}.webp"

    # Skip if thumbnail already exists and is newer than source
    if dst_path.exists() and dst_path.stat().st_mtime >= src_path.stat().st_mtime:
        print(f"Skipping (up to date): {dst_path.name}")
        return

    with Image.open(src_path) as img:
        # Convert to RGBA to avoid issues with palettes / modes
        img = img.convert("RGBA")
        img.thumbnail(THUMB_SIZE, Image.LANCZOS)
        img.save(dst_path, "WEBP", quality=WEBP_QUALITY, method=6)
        print(f"Created thumbnail: {dst_path.name}")


def main() -> None:
    if not SOURCE_DIR.exists():
        raise SystemExit(f"Source directory does not exist: {SOURCE_DIR}")

    image_files = [
        p for p in SOURCE_DIR.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg"}
    ]

    if not image_files:
        print(f"No images found in {SOURCE_DIR}")
        return

    print(f"Found {len(image_files)} images in {SOURCE_DIR}")
    for img_path in image_files:
        make_thumbnail(img_path, THUMB_DIR)

    print("Done generating thumbnails.")


if __name__ == "__main__":
    main()

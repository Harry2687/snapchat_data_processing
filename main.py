import glob
import hashlib
import os
import shutil
import subprocess
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from PIL import Image


def overlay_video(video_file: str, overlay_file: str, output_video_file: str) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-i",
            video_file,
            "-i",
            overlay_file,
            "-filter_complex",
            "[0]split[base][ref];[1][ref]scale=w=rw:h=rh[ov];[base][ov]overlay=0:0",
            "-crf",
            "18",
            "-c:a",
            "copy",
            output_video_file,
        ]
    )


def overlay_image(image_file: str, overlay_file: str, output_image_file: str) -> None:
    background_img = Image.open(image_file)
    background = background_img.convert("RGBA")
    background_exif = background_img.getexif()
    foreground = Image.open(overlay_file).convert("RGBA")

    if background.size != foreground.size:
        print("Warning: Image dimensions are not the same.")
        foreground = foreground.resize(background.size)

    composite_img = Image.alpha_composite(background, foreground)
    composite_img.convert("RGB").save(
        output_image_file, quality=95, exif=background_exif
    )


def process_zipped_memory(zip_path: str, output_path: str) -> None:
    # Extract zip into temp dir
    temp_dir = "./temp"
    with zipfile.ZipFile(zip_path, "r") as zip:
        zip.extractall(temp_dir)

    # Either a video or photo
    video_files = glob.glob(f"{temp_dir}/*.mp4")
    jpg_files = glob.glob(f"{temp_dir}/*.jpg")
    png_files = glob.glob(f"{temp_dir}/*.png")

    # Video memory
    if len(video_files) == 1 and len(png_files) == 1:
        video_file = video_files[0]
        overlay_file = png_files[0]
        output_video_file = video_file.replace("-main", "")

        # Overlay caption onto video
        overlay_video(video_file, overlay_file, output_video_file)

        # Copy to output dir
        os.makedirs(output_path, exist_ok=True)
        shutil.copy(output_video_file, output_path)
        shutil.rmtree(temp_dir)

    # Photo memory
    elif len(jpg_files) == 1 and len(png_files) == 1:
        image_file = jpg_files[0]
        overlay_file = png_files[0]
        output_image_file = image_file.replace("-main", "")

        # Overlay caption onto image
        overlay_image(image_file, overlay_file, output_image_file)

        # Copy to output dir
        os.makedirs(output_path, exist_ok=True)
        shutil.copy(output_image_file, output_path)
        shutil.rmtree(temp_dir)

    else:
        print(f"Memory not in mp4 or jpg format: {zip_path}")


def get_zip_files_in_dir(dir_path: str) -> list[str]:
    zip_files = []
    for item in os.listdir(dir_path):
        full_path = os.path.join(dir_path, item)
        if os.path.isfile(full_path) and zipfile.is_zipfile(full_path):
            zip_files.append(full_path)
    return zip_files


def get_non_zip_files_in_dir(dir_path: str) -> list[str]:
    non_zip_files = []
    for item in os.listdir(dir_path):
        full_path = os.path.join(dir_path, item)
        if os.path.isfile(full_path) and not zipfile.is_zipfile(full_path):
            non_zip_files.append(full_path)
    return non_zip_files


def get_media_overlay_pairs(directory_path: str) -> list[list[str]]:
    files_by_mtime = defaultdict(list)

    for filename in os.listdir(directory_path):
        full_path = os.path.join(directory_path, filename)

        try:
            mtime_sec = int(os.path.getmtime(full_path))

            is_media = "_media" in filename
            is_overlay = "_overlay" in filename

            if is_media or is_overlay:
                files_by_mtime[mtime_sec].append(
                    {"path": full_path, "is_media": is_media, "is_overlay": is_overlay}
                )

        except Exception as e:
            print(f"Could not process file {filename}: {e}")
            continue

    matched_pairs = []

    for mtime, files_list in files_by_mtime.items():
        media_files = [f["path"] for f in files_list if f["is_media"]]
        overlay_files = [f["path"] for f in files_list if f["is_overlay"]]
        mtime_human = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

        if len(media_files) == 1 and len(overlay_files) == 1:
            matched_pairs.append([media_files[0], overlay_files[0], mtime_human])
        elif len(media_files) > 1 and len(overlay_files) > 1:
            # Check if overlay files are all the same
            overlay_hashes = [
                hashlib.md5(open(overlay_file, "rb").read()).hexdigest()
                for overlay_file in overlay_files
            ]
            if len(set(overlay_hashes)) == 1:
                # Pair all media files with the same overlay
                for media_file in media_files:
                    matched_pairs.append([media_file, overlay_files[0], mtime_human])
        elif len(overlay_files) == 0:
            pass
        else:
            print(f"{mtime_human}: Overlay exists without base media.")

    return matched_pairs


def get_non_media_overlay_pairs(directory_path: str) -> list[list[str]]:
    all_files = [
        os.path.join(directory_path, filename)
        for filename in os.listdir(directory_path)
    ]

    media_overlay_pairs = get_media_overlay_pairs(directory_path)
    media_overlay_files = [file for pair in media_overlay_pairs for file in pair[:2]]
    media_overlay_file_set = set(media_overlay_files)

    non_media_overlay_pairs = [
        file for file in all_files if file not in media_overlay_file_set
    ]

    # Other unwanted items
    filter_out_list = ["_thumbnail", "_metadata", "_overlay"]

    non_media_overlay_pairs = [
        file
        for file in non_media_overlay_pairs
        if not any(filter_out in file for filter_out in filter_out_list)
    ]

    return non_media_overlay_pairs


def process_media_overlay_pairs(matched_pairs: list[list], output_path: str) -> None:
    for pair in matched_pairs:
        media_file = pair[0]
        overlay_file = pair[1]
        mtime_human = pair[2]

        media_dir, media_name = os.path.split(media_file)
        new_media_name = media_name.replace("_media", "")
        output_media_file = os.path.join(media_dir, new_media_name)

        media_extension = Path(media_file).suffix.lower()
        if media_extension == ".mp4":
            # Convert overlay to png first since webp sometimes causes issues with ffmpeg
            overlay_extension = Path(overlay_file).suffix.lower()
            if overlay_extension == ".webp":
                overlay_image = Image.open(overlay_file)
                overlay_file_png = overlay_file.replace(overlay_extension, ".png")
                overlay_image.save(overlay_file_png, "PNG")

                overlay_video(media_file, overlay_file_png, output_media_file)

                os.remove(overlay_file_png)
            else:
                overlay_video(media_file, overlay_file, output_media_file)

            # Change modified time to match original file
            original_mtime = os.path.getmtime(media_file)
            os.utime(output_media_file, (original_mtime, original_mtime))
        else:
            print(f"{mtime_human}: No mp4 files.")

        os.makedirs(output_path, exist_ok=True)
        shutil.move(output_media_file, output_path)


def main() -> None:
    memories_path = "./data/memories"
    memories_output_path = "./processed_memories"

    for zip in get_zip_files_in_dir(memories_path):
        process_zipped_memory(zip, memories_output_path)

    for non_zip in get_non_zip_files_in_dir(memories_path):
        shutil.copy(non_zip, memories_output_path)

    chat_media_path = "./data/chat_media"
    chat_media_output_path = "./processed_chat_media"

    media_overlay_pairs = get_media_overlay_pairs(chat_media_path)
    process_media_overlay_pairs(media_overlay_pairs, chat_media_output_path)

    for file_path in get_non_media_overlay_pairs(chat_media_path):
        shutil.copy(file_path, chat_media_output_path)
        original_mtime = os.path.getmtime(file_path)
        _, file_name = os.path.split(file_path)
        os.utime(
            os.path.join(chat_media_output_path, file_name),
            (original_mtime, original_mtime),
        )


if __name__ == "__main__":
    main()

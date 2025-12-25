import hashlib
import logging
import os
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from PIL import Image

from overlay import overlay_video


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
            logging.error(f"Could not process file {filename}: {e}")
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
            logging.error(f"{mtime_human}: Overlay exists without base media.")

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
            logging.info(f"Overlayed and updated timestamp for: {new_media_name}")
        else:
            logging.error(f"{mtime_human}: No mp4 files.")

        os.makedirs(output_path, exist_ok=True)
        shutil.move(output_media_file, output_path)


def process_chat_media_folder(folder_path: str, output_path: str) -> None:
    media_overlay_pairs = get_media_overlay_pairs(folder_path)
    logging.info(f"Found {len(media_overlay_pairs)} media-overlay pairs to process.")

    process_media_overlay_pairs(media_overlay_pairs, output_path)

    non_media_files = get_non_media_overlay_pairs(folder_path)
    logging.info(f"Copying {len(non_media_files)} standalone files...")
    for file_path in non_media_files:
        shutil.copy(file_path, output_path)
        original_mtime = os.path.getmtime(file_path)
        _, file_name = os.path.split(file_path)
        os.utime(
            os.path.join(output_path, file_name),
            (original_mtime, original_mtime),
        )
        logging.info(f"Copied and updated timestamp for: {file_name}")

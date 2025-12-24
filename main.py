import glob
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import piexif
import requests
from PIL import Image

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


# Stuff to overlay captions to videos/images
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


# Stuff to deal with memories
def overlay_zipped_memory(zip_path: str, output_path: str) -> None:
    # Extract zip into temp dir
    with tempfile.TemporaryDirectory() as temp_dir:
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

            # Get final output file
            final_output_path = os.path.join(
                output_path, os.path.basename(output_video_file)
            )

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

            # Get final output file
            final_output_path = os.path.join(
                output_path, os.path.basename(output_image_file)
            )

        else:
            print(f"Memory not in mp4 or jpg format: {zip_path}")

    return final_output_path


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


def add_gps_to_video(file_path, lat, lon):
    # 1. Prepare the ISO 6709 location string
    # Format: ±Lat±Long/ (e.g., -31.9547+115.8602/)
    location_string = f"{lat:+08.4f}{lon:+09.4f}/"

    # 2. Define a temporary filename
    temp_file = "temp_metadata_video.mp4"

    command = [
        "ffmpeg",
        "-y",  # -y overwrites temp_file if it exists
        "-i",
        file_path,
        "-metadata",
        f"location={location_string}",
        "-c",
        "copy",  # Copy streams without re-encoding
        "-map_metadata",
        "0",  # Keep existing metadata
        temp_file,
    ]

    try:
        # 3. Run FFmpeg
        subprocess.run(command, check=True, capture_output=True)

        # 4. Replace the original file with the new one
        os.replace(temp_file, file_path)
        print(f"Successfully updated metadata for {file_path}")

    except subprocess.CalledProcessError as e:
        print(f"Error occurred: {e.stderr.decode()}")
        if os.path.exists(temp_file):
            os.remove(temp_file)


def add_gps_to_image(file_path, lat, lon):
    def decimal_to_dms(value):
        abs_value = abs(value)
        deg = int(abs_value)
        minutes = int((abs_value - deg) * 60)
        seconds = round((abs_value - deg - minutes / 60) * 3600 * 100)
        return (deg, 1), (minutes, 1), (seconds, 100)

    lat_dms = decimal_to_dms(lat)
    lon_dms = decimal_to_dms(lon)

    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: "N" if lat >= 0 else "S",
        piexif.GPSIFD.GPSLatitude: lat_dms,
        piexif.GPSIFD.GPSLongitudeRef: "E" if lon >= 0 else "W",
        piexif.GPSIFD.GPSLongitude: lon_dms,
    }

    exif_dict = piexif.load(file_path)
    exif_dict["GPS"] = gps_ifd

    exif_bytes = piexif.dump(exif_dict)
    piexif.insert(exif_bytes, file_path)


def download_memory(url: str, output_path: str) -> str:
    response = requests.get(url)

    # Look for the 'Content-Disposition' header
    content_disposition = response.headers.get("content-disposition")

    if content_disposition:
        # Use a regex to find the filename attribute
        fname_match = re.findall("filename=(.+)", content_disposition)
        if fname_match:
            # Clean up quotes if present
            filename = fname_match[0].strip('"')
        else:
            # Fallback to the end of the URL if header doesn't have a filename
            filename = url.split("/")[-1]
    else:
        # Fallback to the end of the URL
        filename = url.split("/")[-1]

    file_path = os.path.join(output_path, filename)

    os.makedirs(output_path, exist_ok=True)

    # Save the file using the extracted name
    with open(file_path, "wb") as f:
        f.write(response.content)

    return file_path


def process_memory(url: str, date: str, location: str, output_path: str):
    def set_modified_time(file_path, date):
        date_obj = datetime.strptime(date, "%Y-%m-%d %H:%M:%S %Z")
        timestamp = date_obj.timestamp()
        os.utime(file_path, (timestamp, timestamp))

    with tempfile.TemporaryDirectory() as temp_dir:
        raw_file_path = download_memory(url=url, output_path=temp_dir)
        raw_file_extension = Path(raw_file_path).suffix.lower()

        lat, lon = map(float, re.findall(r"[-+]?\d*\.\d+|\d+", location))

        if raw_file_extension == ".zip":
            overlayed_file_path = overlay_zipped_memory(raw_file_path, temp_dir)
            overlayed_file_extension = Path(overlayed_file_path).suffix.lower()

            if overlayed_file_extension == ".mp4":
                add_gps_to_video(file_path=overlayed_file_path, lat=lat, lon=lon)
            elif overlayed_file_extension == ".jpg":
                add_gps_to_image(file_path=overlayed_file_path, lat=lat, lon=lon)

            set_modified_time(file_path=overlayed_file_path, date=date)

            # Copy to output dir
            os.makedirs(output_path, exist_ok=True)
            shutil.move(overlayed_file_path, output_path)
        else:
            if raw_file_extension == ".mp4":
                add_gps_to_video(file_path=raw_file_path, lat=lat, lon=lon)
            elif raw_file_extension == ".jpg":
                add_gps_to_image(file_path=raw_file_path, lat=lat, lon=lon)

            set_modified_time(file_path=raw_file_path, date=date)

            # Copy to output dir
            os.makedirs(output_path, exist_ok=True)
            shutil.move(raw_file_path, output_path)


# Stuff to deal with chat media
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
    memories_json_path = "./data/memories_history.json"
    memories_output_path = "./data/processed_memories"

    with open(memories_json_path) as f:
        memories_history = json.load(f)

    saved_media = memories_history["Saved Media"]
    total_memories = len(saved_media)

    logging.info(f"Found {total_memories} memories to process.")

    for index, memory in enumerate(saved_media, start=1):
        date = memory["Date"]

        logging.info(f"[{index}/{total_memories}] Processing memory from {date}...")

        process_memory(
            url=memory["Media Download Url"],
            date=date,
            location=memory["Location"],
            output_path=memories_output_path,
        )

    logging.info("Processing complete.")

    # chat_media_path = "./data/chat_media"
    # chat_media_output_path = "./data/processed_chat_media"

    # media_overlay_pairs = get_media_overlay_pairs(chat_media_path)
    # process_media_overlay_pairs(media_overlay_pairs, chat_media_output_path)

    # for file_path in get_non_media_overlay_pairs(chat_media_path):
    #     shutil.copy(file_path, chat_media_output_path)
    #     original_mtime = os.path.getmtime(file_path)
    #     _, file_name = os.path.split(file_path)
    #     os.utime(
    #         os.path.join(chat_media_output_path, file_name),
    #         (original_mtime, original_mtime),
    #     )


if __name__ == "__main__":
    main()

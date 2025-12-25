import glob
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

import piexif
import requests

from .overlay import overlay_image, overlay_video


def overlay_zipped_memory(zip_path: str, output_path: str) -> str:
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
            logging.warning(f"Memory not in mp4 or jpg format: {zip_path}")

    return final_output_path


def add_gps_to_video(file_path: str, lat: float, lon: float) -> None:
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
        logging.info(f"Successfully updated metadata for {file_path}")

    except subprocess.CalledProcessError as e:
        logging.error(f"Error occurred: {e.stderr.decode()}")
        if os.path.exists(temp_file):
            os.remove(temp_file)


def add_gps_to_image(file_path: str, lat: float, lon: float) -> None:
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
    logging.info(f"Successfully updated metadata for {file_path}")


def download_memory(
    url: str, output_path: str, max_retries: int = 3, delay: int = 2
) -> str:
    attempts = 0
    content_disposition = None
    response = None

    while attempts < max_retries:
        response = requests.get(url)
        content_disposition = response.headers.get("content-disposition")

        if content_disposition:
            break  # Found it, exit the loop

        attempts += 1
        logging.warning(
            f"Header not found. Attempt {attempts}/{max_retries}. Retrying in {delay}s..."
        )
        time.sleep(delay)

    # Logic for filename extraction
    if content_disposition:
        fname_match = re.findall("filename=(.+)", content_disposition)
        filename = fname_match[0].strip('"') if fname_match else url.split("/")[-1]
    else:
        # Final fallback if retries failed
        filename = url.split("/")[-1]

    file_path = os.path.join(output_path, filename)
    os.makedirs(output_path, exist_ok=True)

    with open(file_path, "wb") as f:
        f.write(response.content)

    return file_path


def process_memory(url: str, date: str, location: str, output_path: str) -> None:
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


def process_memory_json(json_path: str, output_path: str) -> None:
    with open(json_path) as f:
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
            output_path=output_path,
        )

    logging.info("Processing complete.")

import glob
import os
import shutil
import subprocess
import zipfile

from PIL import Image


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

        # Overlap caption onto video
        subprocess.run(
            [
                "ffmpeg",
                "-i",
                video_file,
                "-i",
                overlay_file,
                "-filter_complex",
                "[1][0]scale2ref=w=iw:h=ih[ov][base];[base][ov]overlay=0:0",
                "-crf",
                "18",
                "-c:a",
                "copy",
                output_video_file,
            ]
        )

        # Copy to output dir
        shutil.copy(output_video_file, output_path)
        shutil.rmtree(temp_dir)

    # Photo memory
    elif len(jpg_files) == 1 and len(png_files) == 1:
        image_file = jpg_files[0]
        overlap_file = png_files[0]
        output_image_file = image_file.replace("-main", "")

        background = Image.open(image_file).convert("RGBA")
        foreground = Image.open(overlap_file).convert("RGBA")

        if background.size != foreground.size:
            print(
                "Warning: Image dimensions are not the same. This method requires them to be identical."
            )
            foreground = foreground.resize(background.size)

        composite_img = Image.alpha_composite(background, foreground)
        composite_img.convert("RGB").save(output_image_file, quality=95)

        # Copy to output dir
        shutil.copy(output_image_file, output_path)
        shutil.rmtree(temp_dir)

    else:
        print(f"Memory not in mp4 or jpg format: {zip_path}")


def get_zip_files_in_dir(dir_path):
    zip_files = []
    for item in os.listdir(dir_path):
        full_path = os.path.join(dir_path, item)
        if os.path.isfile(full_path) and zipfile.is_zipfile(full_path):
            zip_files.append(full_path)
    return zip_files


def get_non_zip_files_in_dir(dir_path):
    non_zip_files = []
    for item in os.listdir(dir_path):
        full_path = os.path.join(dir_path, item)
        if os.path.isfile(full_path) and not zipfile.is_zipfile(full_path):
            non_zip_files.append(full_path)
    return non_zip_files


def main() -> None:
    input_path = "./data/memories"
    output_path = "./processed_memories"

    for zip in get_zip_files_in_dir(input_path):
        process_zipped_memory(zip, output_path)

    for non_zip in get_non_zip_files_in_dir(input_path):
        shutil.copy(non_zip, output_path)


if __name__ == "__main__":
    main()

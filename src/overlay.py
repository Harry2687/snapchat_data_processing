import subprocess

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

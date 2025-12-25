# Snapchat Data Processing

This is a script I used to process my Snapchat data (memories and chat media) after it was exported via account settings. It's not really intended for users but it's easy enough to change input and output paths in `main.py`, the functions in `src` should also be pretty reusable.

This project's environment is mananaged using `uv`.

## Processing Logic

### Memories (src/memories.py)

The `src/memories.py` script is responsible for processing exported Snapchat memories. The main steps involve:

1.  **Reading Memories Data:** It reads a `memories_history.json` file, which contains metadata for all saved memories, including download URLs, creation dates, and location information.
2.  **Downloading Media:** For each memory, the script downloads the raw media (either a photo or a video) from the provided URL. These raw files can sometimes be zipped if they contain an overlay.
3.  **Overlaying Captions:** If a memory is a zipped file (indicating it has a caption overlay), the script extracts the main media and the overlay image. It then uses FFmpeg (for videos) or PIL (for images) to burn the caption overlay directly onto the media.
4.  **Adding GPS Metadata:** Using the location data from the `memories_history.json`, the script embeds GPS coordinates into the processed media file. For videos, this is done using FFmpeg to add ISO 6709 location metadata. For images, `piexif` is used to add EXIF GPS data.
5.  **Setting Modified Time:** The file's modified timestamp is updated to reflect the original creation date of the memory.

### Chat Media (src/chatmedia.py)

The `src/chatmedia.py` script handles the processing of media exported from Snapchat chats. The process is as follows:

1.  **Identifying Media-Overlay Pairs:** The script scans the chat media folder to identify pairs of media files (e.g., `image_media.jpg`) and their corresponding overlay files (e.g., `image_overlay.webp`). These pairs are identified based on their filenames and modification times.
2.  **Overlaying Captions on Videos:** For identified media-overlay pairs that are videos (`.mp4`), the script uses FFmpeg to overlay the caption onto the video. If the overlay is in `.webp` format, it's first converted to `.png` for compatibility. Note: my data export didn't seem to separate chat media images into a base and overlay file so I just didn't implement overlaying for chat media images (it is implemented for memories).
3.  **Renaming and Timestamping:** The processed media files are renamed by removing the `_media` suffix. The modified timestamp of the processed file is also updated to match the original media file's modification time.
4.  **Copying Standalone Files:** Any files in the chat media folder that are not part of a media-overlay pair (i.e., standalone photos or videos without captions) are copied directly to the output directory, maintaining their original modified times.

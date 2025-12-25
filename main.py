import logging
import os
import shutil

from src.chatmedia import (
    get_media_overlay_pairs,
    get_non_media_overlay_pairs,
    process_media_overlay_pairs,
)
from src.memories import process_memory_json

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def main() -> None:
    memories_json_path = "./data/memories_history.json"
    memories_output_path = "./data/processed_memories"
    process_memory_json(json_path=memories_json_path, output_path=memories_output_path)

    chat_media_path = "./data/chat_media"
    chat_media_output_path = "./data/processed_chat_media"

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

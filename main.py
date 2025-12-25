import json
import logging
import os
import shutil

from src.chatmedia import (
    get_media_overlay_pairs,
    get_non_media_overlay_pairs,
    process_media_overlay_pairs,
)
from src.memories import process_memory

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

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

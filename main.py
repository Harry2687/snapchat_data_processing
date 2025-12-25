import logging

from src.chatmedia import process_chat_media_folder
from src.memories import process_memory_json

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def main() -> None:
    memories_json_path = "./data/memories_history.json"
    memories_output_path = "./data/processed_memories_v2"
    process_memory_json(json_path=memories_json_path, output_path=memories_output_path)

    chat_media_path = "./data/chat_media_v2"
    chat_media_output_path = "./data/processed_chat_media_v2"
    process_chat_media_folder(
        folder_path=chat_media_path, output_path=chat_media_output_path
    )


if __name__ == "__main__":
    main()

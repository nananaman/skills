import argparse
from pathlib import Path

from task_data import load_tasks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    for task in load_tasks(args.file):
        print(f"{task.id}: {task.title}")


if __name__ == "__main__":
    main()

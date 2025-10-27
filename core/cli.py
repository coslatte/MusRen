"""
CLI entry point for the Music Renamer application.
Handles command line arguments and executes corresponding operations.
"""

import os
import argparse
from constants.info import PARSER_DESCRIPTION
from core.audio_processor import AudioProcessor
from utils.dependencies import check_dependencies
from utils.tools import get_audio_files


class Cli:
    args: argparse.Namespace = None
    processor: AudioProcessor = None
    parser: argparse.ArgumentParser = None

    def __init__(self):
        self.parser = argparse.ArgumentParser(description=PARSER_DESCRIPTION)
        self._init_parser()
        self.args = self.parser.parse_args()
        self.processor = AudioProcessor(
            directory=self.args.directory, acoustid_api_key=self.args.acoustid_key
        )

    def _verify_sync_lyrics(self) -> None:
        use_acoustid = self.args.recognition

        start_lyrics = input(
            "Start searching and embedding lyrics? (Y/N): "
        ).lower()
        if start_lyrics == "y":
            lyrics_results = self.processor.process_files(
                use_recognition=use_acoustid, process_lyrics=True
            )

            # Show processing statistics
            if lyrics_results:
                total = len(lyrics_results)
                recognized = sum(
                    1 for f, r in lyrics_results.items() if r.get("recognition", False)
                )
                lyrics_found = sum(
                    1 for f, r in lyrics_results.items() if r.get("lyrics_found", False)
                )
                lyrics_embedded = sum(
                    1
                    for f, r in lyrics_results.items()
                    if r.get("lyrics_embedded", False)
                )

                print("\nSummary:")
                print(f"Total files processed: {total}")
                if use_acoustid:
                    print(f"Songs recognized: {recognized}")
                print(f"Lyrics found: {lyrics_found}")
                print(f"Lyrics embedded successfully: {lyrics_embedded}")

    def _add_covers(self) -> None:
        # Import the specific cover processor
        try:
            import core.install_covers as install_covers

            print("Executing add covers...")
            install_covers.main()
            return
        except ImportError:
            print("Error importing the cover installation module.")
            return

    def _init_parser(self) -> None:
        self.parser.add_argument(
            "-d",
            "--directory",
            help="Directory where audio files are located",
            default=".",
        )
        self.parser.add_argument(
            "-l",
            "--lyrics",
            help="Search and embed synchronized lyrics",
            action="store_true",
        )
        self.parser.add_argument(
            "--recognition",
            help="Use audio recognition with AcoustID",
            action="store_true",
        )
        self.parser.add_argument(
            "--acoustid_key",
            help="AcoustID API key (optional)",
            default="8XaBELgH",
        )
        self.parser.add_argument(
            "--only-covers",
            help="Add album covers only",
            action="store_true",
        )
        self.parser.add_argument(
            "--albums",
            help="Organize files into album folders after processing",
            action="store_true",
        )

    def main(self) -> None:
        """Main function of the command line interface."""

        # Check dependencies
        print("Checking dependencies...\n")
        if not check_dependencies(use_recognition=self.args.recognition):
            return

        directory = os.path.abspath(self.args.directory)
        print(f"Working directory: {directory}")

        if not os.path.isdir(directory):
            print(f"The specified directory does not exist: {directory}")
            input("Press Enter to exit...")
            return

        files = get_audio_files(directory)

        if not files:
            print("No audio files found in this directory.")
            input("Press Enter to exit...")
            return

        print(f"Found {len(files)} audio files.")

        # If we only want to add covers
        if self.args.only_covers:
            print("Mode: Add album covers only")
            self._add_covers()

        # Check if we should search for synchronized lyrics
        if self.args.lyrics:
            print(
                "The synchronized lyrics search and embedding function will be used."
            )
            self._verify_sync_lyrics()

        # Rename files
        start_rename = input("Start renaming files? (Y/N): ").lower()
        if start_rename != "y":
            print("Renaming operation cancelled.")
            input("Press Enter to exit...")
            return

        changes = self.processor.rename_files()

        if changes:
            keep_changes = input(
                "Do you want to keep the name changes? (Y/N): "
            ).lower()
            if keep_changes != "y":
                self.processor.undo_rename(changes)
                print("The name changes have been reverted.")
            else:
                print("The name changes have been kept.")
        else:
            print("No name changes were made.")

        print("The process has completed successfully.")
        input("Press Enter to exit...")

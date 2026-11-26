"""Credential hygiene: nothing key-shaped in the repository, and .env can never be committed."""
import unittest
from pathlib import Path

from brief.reviewer import SECRET_PATTERNS

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "__pycache__"}
TEXT_SUFFIXES = {".py", ".json", ".md", ".html", ".txt", ".example", ".gitignore", ""}


def project_files():
    for path in ROOT.rglob("*"):
        if path.is_file() and not (set(path.parts) & SKIP_DIRS) and path.suffix in TEXT_SUFFIXES:
            yield path


class RepoHygiene(unittest.TestCase):
    def test_no_secret_shaped_strings_in_any_file(self):
        hits = []
        for path in project_files():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for label, pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    hits.append(f"{path.relative_to(ROOT)}: {label}")
        self.assertEqual(hits, [])

    def test_gitignore_blocks_env_files(self):
        lines = (ROOT / ".gitignore").read_text().splitlines()
        self.assertIn(".env", lines)

    def test_no_env_file_is_present(self):
        self.assertFalse((ROOT / ".env").exists())

    def test_env_example_has_no_values(self):
        for line in (ROOT / ".env.example").read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                self.assertEqual(line.split("=", 1)[1].strip(), "", line)


if __name__ == "__main__":
    unittest.main()

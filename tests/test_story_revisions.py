from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from story_builder.services.story_revisions import create_revision, get_revision, list_revisions


class StoryRevisionTests(unittest.TestCase):
    def test_revisions_are_immutable_and_linked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = create_revision(root, "novel", "Beginning")
            second = create_revision(root, "novel", "Beginning\nEnding", parent_revision_id=first["revision_id"])
            self.assertEqual(get_revision(root, "novel", first["revision_id"])["content"], "Beginning")
            self.assertEqual(second["parent_revision_id"], first["revision_id"])
            self.assertEqual(len(list_revisions(root, "novel")), 2)

    def test_rejects_unknown_kind(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                create_revision(Path(directory), "unknown", "text")


if __name__ == "__main__":
    unittest.main()

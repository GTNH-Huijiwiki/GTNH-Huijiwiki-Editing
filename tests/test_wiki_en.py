"""英文镜像（只读）的行为：增量同步、本地文件保护、标题撞名、改名标记、与中文站隔离。

不访问网络。运行：python -m unittest discover -s tests
"""

import importlib.util
import json
import os
import tempfile
import unittest
from unittest.mock import patch

_SOURCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir,
                       "skills", "gtnh-wiki-editing", "scripts", "wiki.py")
_spec = importlib.util.spec_from_file_location("wiki_under_test", _SOURCE)
wiki = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wiki)


class FakeEnglishWiki:
    """按 formatversion=2 的形状回答脚本用到的查询。"""

    def __init__(self):
        self.pages = {}  # pageid → dict(title, text, revid)
        self.moves = {}
        self.calls = []
        self.split_content = False

    def add(self, pageid, title, text, revid, ns=0):
        self.pages[pageid] = {"title": title, "text": text, "revid": revid, "ns": ns}

    def __call__(self, **query):
        self.calls.append(query)
        if query.get("meta") == "siteinfo":
            return {"query": {"namespaces": {"-1": {}, "0": {}, "10": {}}}}
        if query.get("list") == "allpages":
            return {"query": {"allpages": [
                {"pageid": n, "ns": p["ns"], "title": p["title"]}
                for n, p in self.pages.items() if str(p["ns"]) == query["apnamespace"]]}}
        if query.get("list") == "logevents":
            target = self.moves.get(query["letitle"])
            events = [{"type": "move", "action": "move", "timestamp": "2026-11-10T00:00:00Z",
                       "params": {"target_title": target}}] if target else []
            return {"query": {"logevents": events}}
        if "revids" in query:
            for page in self.pages.values():
                return {"query": {"pages": [{"title": page["title"], "revisions": [
                    {"revid": int(query["revids"]), "timestamp": "2026-01-01T00:00:00Z",
                     "slots": {"main": {"content": "old line"}}}]}]}}
        content = "content" in query.get("rvprop", "")
        normalized = []
        if "pageids" in query:
            wanted = [int(n) for n in query["pageids"].split("|")]
            result = []
        else:
            wanted, result = [], []
            for requested in query["titles"].split("|"):
                title = requested.replace("_", " ")
                if title != requested:
                    normalized.append({"from": requested, "to": title})
                found = [n for n, p in self.pages.items() if p["title"] == title]
                if found:
                    wanted += found
                else:
                    result.append({"title": title, "ns": 0, "missing": True})
        for n in wanted:
            page = self.pages[n]
            revision = {"revid": page["revid"], "timestamp": "2026-11-01T00:00:00Z"}
            if content:
                revision["slots"] = {"main": {"content": page["text"], "contentmodel": "wikitext"}}
            entry = {"pageid": n, "ns": page["ns"], "title": page["title"], "contentmodel": "wikitext",
                     "revisions": [revision]}
            if page["text"].startswith("#REDIRECT"):
                entry["redirect"] = True
            result.append(entry)
        answer = {"query": {"pages": result, "normalized": normalized}}
        if content and self.split_content and len(result) > 1:
            if "rvcontinue" not in query:
                answer["query"]["pages"] = [result[0]] + [
                    {k: v for k, v in p.items() if k != "revisions"} for p in result[1:]]
                answer["continue"] = {"rvcontinue": "x", "continue": "||"}
            else:
                answer["query"]["pages"] = [
                    {k: v for k, v in result[0].items() if k != "revisions"}] + result[1:]
        return answer


class EnglishMirrorTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.en = os.path.join(directory.name, "wikitext-en")
        self.zh = os.path.join(directory.name, "wikitext")
        self.site = FakeEnglishWiki()
        self.site.add(1, "Machine", "first", 11)
        self.site.add(2, "machine", "#REDIRECT [[Machine]]", 12)
        for name, value in [("EN_DIR", self.en), ("WIKI_DIR", self.zh), ("en_api", self.site)]:
            patcher = patch.object(wiki, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.log = []

    def pull(self, *titles, **kwargs):
        return wiki.pull_en(list(titles), report=self.log.append, **kwargs)

    def records(self):
        with open(os.path.join(self.en, ".revisions.json"), encoding="utf-8") as f:
            return json.load(f)

    def path(self, title):
        return os.path.join(self.en, self.records()[title]["path"])

    def read(self, title):
        with open(self.path(title), encoding="utf-8") as f:
            return f.read()

    def write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def changes(self):
        with open(os.path.join(self.en, ".changes.tsv"), encoding="utf-8") as f:
            return [line.split("\t") for line in f.read().splitlines()[1:]]

    def test_incremental_pull_records_revisions_and_changes(self):
        stats = self.pull(all_pages=True)
        self.assertEqual(stats["added"], ["Machine", "machine"])
        self.assertEqual(self.records()["Machine"]["revid"], 11)
        self.assertTrue(self.records()["machine"]["redirect"])
        self.site.calls.clear()
        self.assertEqual(self.pull(all_pages=True)["unchanged"], 2)
        self.assertFalse(any("content" in q.get("rvprop", "") for q in self.site.calls))
        self.site.add(1, "Machine", "second", 21)
        self.assertEqual(self.pull(all_pages=True)["updated"], ["Machine"])
        self.assertEqual(self.read("Machine"), "second")
        self.assertEqual(self.changes()[-1][1:5], ["更新", "Machine", "11", "21"])

    def test_titles_differing_only_in_case_get_separate_files(self):
        self.pull("Machine", "machine")
        first, second = self.path("Machine"), self.path("machine")
        self.assertNotEqual(first.casefold(), second.casefold())
        self.assertEqual(wiki.path_to_title(first), "Machine")
        self.assertEqual(wiki.path_to_title(second), "machine")

    def test_underscored_title_is_stored_under_normalized_title(self):
        self.site.add(3, "Long Pipeline", "pipe", 13)
        path = wiki.pull("Long_Pipeline", en=True)
        self.assertEqual(wiki.path_to_title(path), "Long Pipeline")

    def test_local_edit_is_kept_unless_forced(self):
        self.pull("Machine")
        self.write(self.path("Machine"), "local edit")
        self.assertEqual(self.pull("Machine")["conflicts"], ["Machine"])
        self.assertEqual(self.read("Machine"), "local edit")
        self.assertEqual(self.pull("Machine", force=True)["restored"], ["Machine"])
        self.assertEqual(self.read("Machine"), "first")

    def test_untracked_file_is_not_overwritten(self):
        target = wiki.title_to_path("Machine", "wikitext", root=self.en)
        self.write(target, "mine")
        self.assertEqual(self.pull("Machine")["conflicts"], ["Machine"])
        with open(target, encoding="utf-8") as f:
            self.assertEqual(f.read(), "mine")

    def test_interrupted_batch_keeps_records_of_written_files(self):
        self.pull(all_pages=True)
        self.site.add(1, "Machine", "second", 21)
        self.site.add(2, "machine", "third", 22)

        def interrupt(message):
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            wiki.pull_en(["Machine", "machine"], report=interrupt)
        stats = self.pull("Machine", "machine")
        self.assertEqual(stats["conflicts"], [])
        self.assertEqual(self.read("machine"), "third")

    def test_missing_local_file_is_downloaded_again(self):
        self.pull("Machine")
        os.remove(self.path("Machine"))
        self.assertEqual(self.pull("Machine")["restored"], ["Machine"])

    def test_renamed_page_is_marked_and_file_kept(self):
        self.pull(all_pages=True)
        self.site.add(1, "New Machine", "first", 31)
        self.site.moves["Machine"] = "New Machine"
        stats = self.pull(all_pages=True)
        self.assertEqual(stats["gone"], ["Machine"])
        self.assertEqual(stats["added"], ["New Machine"])
        self.assertIn("New Machine", self.records()["Machine"]["gone"])
        self.assertTrue(os.path.exists(self.path("Machine")))
        self.assertEqual(self.pull(all_pages=True)["gone"], [])

    def test_other_namespaces_are_not_marked_gone(self):
        self.site.add(4, "Template:Box", "box", 14, ns=10)
        self.pull(all_pages=True)
        self.assertEqual(self.pull(all_pages=True, namespaces=[0])["gone"], [])

    def test_missing_title_is_reported(self):
        stats = self.pull("Nothing")
        self.assertEqual(stats["unavailable"], ["Nothing"])
        with self.assertRaises(RuntimeError):
            wiki.pull("Nothing", en=True)

    def test_content_split_across_continuations_is_merged(self):
        self.site.split_content = True
        stats = self.pull("Machine", "machine")
        self.assertEqual(sorted(stats["added"]), ["Machine", "machine"])
        self.assertEqual(stats["unavailable"], [])

    def test_english_files_cannot_be_pushed(self):
        self.pull("Machine")
        with patch.object(wiki, "api_post", side_effect=AssertionError("不应请求中文站")), \
                patch.object(wiki, "api_get", side_effect=AssertionError("不应请求中文站")):
            with self.assertRaisesRegex(RuntimeError, "只读"):
                wiki.push(self.path("Machine"), "摘要")

    def test_chinese_paths_are_unchanged(self):
        path = wiki.title_to_path("模板:条目")
        self.assertTrue(path.startswith(self.zh + os.sep))
        self.assertEqual(wiki.path_to_title(path), "模板:条目")
        self.assertFalse(wiki.is_en_path(path))

    def test_mirrors_must_be_separate(self):
        with patch.object(wiki, "EN_DIR", os.path.join(self.zh, "en")):
            with self.assertRaisesRegex(RuntimeError, "分开"):
                self.pull("Machine")

    def test_diff_since_rejects_revision_of_another_page(self):
        self.assertIn("-old line", wiki.en_diff_since("Machine", 5))
        with self.assertRaisesRegex(RuntimeError, "属于页面"):
            wiki.en_diff_since("machine", 5)


class SentenceChangeTests(unittest.TestCase):
    OLD = """== One ==
Alpha machine needs steel plates. Beta machine needs copper wires.
== Two ==
* LATEX: coats cables with rubber.
* LESU: old energy storage. Deprecated as of Version 2.8.0.
Gamma sentence will disappear completely."""
    NEW = """== Two ==
* LATEX: coats cables with rubber.
* LESU: old energy storage. Deprecated as of Version 2.9.1.
== Moved ==
Beta machine needs [[copper|copper wires]].
Alpha machine needs ''steel'' plates.
Delta machine is completely brand new here."""

    def test_moves_and_markup_are_ignored(self):
        added, removed = wiki.sentence_changes(self.OLD, self.NEW)
        self.assertEqual([a["sentence"] for a in added],
                         ["Deprecated as of Version 2.9.1.", "Delta machine is completely brand new here."])
        self.assertEqual([s for _, s in removed], ["Gamma sentence will disappear completely."])

    def test_changed_sentence_reports_words_and_its_line(self):
        added, removed = wiki.sentence_changes(self.OLD, self.NEW)
        text = wiki._format_sentence_changes(added, removed)
        self.assertIn("所在行：* LESU: old energy storage.", text)
        self.assertIn("“8”→“9”", text)
        self.assertIsNone(added[1]["old"])


class UnlistedChangeTests(unittest.TestCase):
    def test_short_cells_and_link_targets_are_reported(self):
        old = """|-
| 2.8.X
| [https://example.org/main.zip Download]
| A sentence long enough to compare."""
        new = """|-
| 2.9.X
| [https://example.org/v1.zip Download]
| A sentence long enough to compare."""
        self.assertEqual(wiki.unlisted_changes(old, new),
                         ["- | 2.8.X", "+ | 2.9.X",
                          "- https://example.org/main.zip", "+ https://example.org/v1.zip"])

    def test_moved_rows_are_not_reported(self):
        self.assertEqual(wiki.unlisted_changes("""| EV
|-
| HV""", """| HV
|-
| EV"""), [])


class PreviewCommandTests(unittest.TestCase):
    def test_missing_file_is_rejected_before_rendering(self):
        argv = ["wiki.py", "preview", "-f", "wikitext/no-such-page.wikitext"]
        with patch.object(wiki.sys, "argv", argv), patch.object(wiki, "check") as check:
            with self.assertRaises(RuntimeError):
                wiki._cli()
        check.assert_not_called()


class EnglishRequestTests(unittest.TestCase):
    def test_no_chinese_credentials_are_sent(self):
        sent = []
        with patch.object(wiki, "AUTHKEY", "secret-key"), \
                patch.object(wiki, "_en_send", side_effect=lambda r: sent.append(r) or {"query": {}}):
            wiki.en_api(action="query")
        headers = {k.lower() for k, _ in sent[0].header_items()}
        self.assertEqual(headers, {"user-agent"})
        self.assertNotIn(b"secret-key", sent[0].data)
        self.assertTrue(sent[0].full_url.startswith("https://wiki.gtnewhorizons.com/"))


if __name__ == "__main__":
    unittest.main()

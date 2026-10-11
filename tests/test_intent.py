"""Tests for AZZX v10.6.6: smart intent router (`azzx do`)."""
from __future__ import annotations

import unittest


class IntentTest(unittest.TestCase):
    def _t(self, text):
        from azzx.agent.intent import route
        return route(text)[0]

    def test_fix(self):
        self.assertEqual(self._t("perbaiki bug login"), "fix")
        self.assertEqual(self._t("fix null pointer"), "fix")
        self.assertEqual(self._t("ada error di fungsi login"), "fix")
        # "kenapa ..." is a genuine question -> ask
        self.assertEqual(self._t("kenapa error terus"), "ask")

    def test_implement(self):
        self.assertEqual(self._t("buatkan fungsi hitung diskon"), "implement")
        self.assertEqual(self._t("tambah fitur export csv"), "implement")
        self.assertEqual(self._t("bikin halaman about"), "implement")

    def test_plan_vs_implement_tiebreak(self):
        # "buatkan" is generic; the object decides.
        self.assertEqual(self._t("buatkan rencana migrasi database"), "plan")
        self.assertEqual(self._t("buatkan fungsi hitung diskon"), "implement")

    def test_first_word_wins(self):
        self.assertEqual(self._t("debug kenapa main.py crash"), "debug")
        self.assertEqual(self._t("review kode ini"), "review")
        self.assertEqual(self._t("test unit auth"), "test")

    def test_web(self):
        self.assertEqual(self._t("cari harga kopi hari ini"), "web")

    def test_memory(self):
        self.assertEqual(self._t("ingat bahwa saya suka kopi"), "remember")
        self.assertEqual(self._t("tolong ringkas file besar.txt"), "compress")

    def test_fallback_ask(self):
        self.assertEqual(self._t("halo apa kabar"), "ask")
        self.assertEqual(self._t(""), "ask")

    def test_system_intents(self):
        self.assertEqual(self._t("cek kesehatan sistem"), "doctor")
        self.assertEqual(self._t("buatkan checkpoint project ini"), "checkpoint")
        self.assertEqual(self._t("lihat jadwal saya"), "schedule")
        self.assertEqual(self._t("audit pekerjaan terakhir"), "audit")

    def test_task_cleaned(self):
        from azzx.agent.intent import route
        target, task, _ = route("perbaiki bug login")
        self.assertEqual(target, "fix")
        self.assertEqual(task, "bug login")

    def test_do_parser(self):
        import azzx_cli as a
        p = a.build_parser()
        args = p.parse_args(["do", "perbaiki", "bug"])
        self.assertEqual(args.command, "do")
        self.assertEqual(args.text, ["perbaiki", "bug"])
        args = p.parse_args(["help"])
        self.assertEqual(args.command, "help")

    def test_curated_help_is_small(self):
        import azzx_cli as a
        # The curated front door must stay small; everything else still works.
        self.assertLessEqual(len(a.CURATED_HELP), 32)
        for must in ("do", "help", "chat", "gui", "fix", "ask", "self-update"):
            self.assertIn(must, a.CURATED_HELP)


if __name__ == "__main__":
    unittest.main()

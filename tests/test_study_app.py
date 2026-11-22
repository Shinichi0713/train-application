"""問題生成・アカウント・ポイント・API の基本テスト。"""
from __future__ import annotations

import os
import tempfile
import unittest

from study_app.config import load_kanji
from study_app.generator.base import answers_match
from study_app.generator.registry import SUBJECTS, config, generate_quiz
from study_app.store import ProgressStore


class GeneratorTests(unittest.TestCase):
    def test_kanji_dataset(self):
        items = load_kanji()
        self.assertEqual(len(items), 1026)
        self.assertTrue(all(item["readings"] for item in items))
        self.assertFalse(any("なし" in item["readings"] and item["char"] != "梨" for item in items))

    def test_config_shape(self):
        data = config()
        self.assertEqual(len(data["grades"]), 6)
        self.assertEqual([s["key"] for s in data["subjects"]], ["math", "japanese"])
        self.assertTrue(data["topics"]["math"]["1"])
        self.assertTrue(data["topics"]["japanese"]["6"])

    def test_every_topic_generates_valid_questions(self):
        for subject, entry in SUBJECTS.items():
            for grade in range(1, 7):
                for topic, _ in entry["topics"][grade]:
                    with self.subTest(subject=subject, grade=grade, topic=topic):
                        questions = generate_quiz(subject, grade, [topic], 5, seed=123)
                        self.assertEqual(len(questions), 5)
                        for question in questions:
                            self.assertEqual(question.subject, "算数" if subject == "math" else "国語")
                            self.assertEqual(question.grade, grade)
                            self.assertTrue(question.prompt)
                            self.assertTrue(question.answer)
                            self.assertTrue(question.explanation)
                            if question.choices:
                                self.assertIn(question.answer, question.choices)
                            self.assertNotIn("answer", question.public())

    def test_answer_normalization(self):
        self.assertTrue(answers_match("１２", 12))
        self.assertTrue(answers_match("25 %", "25%"))
        self.assertTrue(answers_match("3/4", "0.75"))
        self.assertFalse(answers_match("5", 6))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ProgressStore(os.path.join(self.tmp.name, "test.sqlite3"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_guest_account_created(self):
        accounts = self.store.list_accounts()
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["nickname"], "ゲスト")
        self.assertFalse(accounts[0]["has_pin"])

    def test_record_and_summary(self):
        account = self.store.create_account("テスト", "1234")
        self.store.record("算数", 3, "calc_add", "1 + 1", True, "2", "2", account["id"])
        self.store.record("国語", 3, "reading", "きょうは？", False, "きのう", "きょう", account["id"])
        summary = self.store.summary(account["id"])
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["correct"], 1)
        self.assertEqual(summary["accuracy"], 50.0)
        self.assertEqual(len(summary["recent_wrong"]), 1)

    def test_pin_and_points(self):
        account = self.store.create_account("さくら", "1234")
        with self.assertRaises(PermissionError):
            self.store.login(account["id"], "0000")
        logged = self.store.login(account["id"], "1234")
        self.assertGreaterEqual(logged["total_points"], 5)  # デイリーボーナス
        self.store.add_points(account["id"], "正解", 10)
        self.store.set_streak(account["id"], 5)
        progress = self.store.account_progress(account["id"])
        self.assertEqual(progress["account"]["streak"], 5)
        self.assertEqual(progress["account"]["best_streak"], 5)
        self.assertIn("正解", [item["reason"] for item in progress["point_breakdown"]])

    def test_migration_from_old_schema(self):
        import sqlite3
        path = os.path.join(self.tmp.name, "old.sqlite3")
        conn = sqlite3.connect(path)
        conn.execute("""
            CREATE TABLE answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                subject TEXT NOT NULL, grade INTEGER NOT NULL, topic TEXT NOT NULL,
                prompt TEXT NOT NULL, correct INTEGER NOT NULL,
                given_answer TEXT NOT NULL, correct_answer TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO answers (subject, grade, topic, prompt, correct, given_answer, correct_answer) "
            "VALUES ('算数', 1, 'calc_add', '1 + 1', 1, '2', '2')"
        )
        conn.commit()
        conn.close()

        store = ProgressStore(path)
        accounts = store.list_accounts()
        self.assertEqual(accounts[0]["nickname"], "ゲスト")
        row = sqlite3.connect(path).execute("SELECT account_id FROM answers").fetchone()
        self.assertEqual(row[0], accounts[0]["id"])

    def test_clear_account(self):
        account = self.store.create_account("クリア", "1234")
        self.store.add_points(account["id"], "正解", 10)
        self.store.clear(account["id"])
        progress = self.store.account_progress(account["id"])
        self.assertEqual(progress["account"]["total_points"], 0)
        self.assertEqual(progress["summary"]["total"], 0)


    def test_analysis_and_mission_claim(self):
        account = self.store.create_account("分析", "1234")
        aid = account["id"]
        # 5問回答してミッション達成
        for i in range(5):
            self.store.record("算数", 3, "calc_add", f"1+{i}", i % 2 == 0, "2", "2", aid)
        analysis = self.store.analysis(aid)
        self.assertEqual(analysis["today"]["answered"], 5)
        self.assertTrue(any(m["key"] == "daily_answer_5" and m["done"] for m in analysis["missions"]))
        # 受け取り
        claimed = self.store.claim_mission(aid, "daily_answer_5")
        mission = next(m for m in claimed["missions"] if m["key"] == "daily_answer_5")
        self.assertTrue(mission["claimed"])
        self.assertGreater(claimed["account"]["total_points"], 0)
        # 二重受け取りは不可
        with self.assertRaises(ValueError):
            self.store.claim_mission(aid, "daily_answer_5")


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ProgressStore(os.path.join(self.tmp.name, "worker.sqlite3"))
        self.account = self.store.create_account("はたらく", "1234")
        self.store.add_points(self.account["id"], "テスト", 1000)

    def tearDown(self):
        self.tmp.cleanup()

    def _db_path(self):
        return self.store.path

    def _set_worker_ready(self, worker_key, seconds_ago=999):
        import sqlite3
        from datetime import datetime, timedelta
        moment = (datetime.now() - timedelta(seconds=seconds_ago)).isoformat(timespec="seconds")
        with sqlite3.connect(self._db_path()) as conn:
            conn.execute(
                "UPDATE farm_workers SET ready_at = ? WHERE account_id = ? AND worker_key = ?",
                (moment, self.account["id"], worker_key),
            )

    def test_encounter_hire_and_collect(self):
        aid = self.account["id"]
        # streak 5 の正解でタロウに出会う
        for i in range(5):
            self.store.record("算数", 1, "calc_add", f"1+{i}", True, "2", "2", aid)
        encounters = self.store.check_worker_encounters(aid, correct=True, streak=5)
        keys = [e["worker_key"] for e in encounters]
        self.assertIn("taro", keys)

        farm = self.store.get_farm(aid)
        taro = next(w for w in farm["workers"] if w["key"] == "taro")
        self.assertFalse(taro["hired"])

        # 雇用にはポイント+食料が必要。食料を足す
        import sqlite3
        with sqlite3.connect(self._db_path()) as conn:
            conn.execute(
                "INSERT INTO farm_inventory (account_id, resource, amount) VALUES (?, 'food', 20) "
                "ON CONFLICT(account_id, resource) DO UPDATE SET amount = amount + 20",
                (aid,),
            )

        before_wallet = self.store.get_account(aid)["wallet"]
        farm = self.store.hire_worker(aid, "taro")
        after = self.store.get_account(aid)
        self.assertEqual(before_wallet - after["wallet"], 120)
        taro = next(w for w in farm["workers"] if w["key"] == "taro")
        self.assertTrue(taro["hired"])
        self.assertEqual(farm["inventory"]["food"], 10)  # 20 - 10

        # まだ働き中は受け取れない
        with self.assertRaises(ValueError):
            self.store.collect_worker(aid, "taro")

        self._set_worker_ready("taro")
        farm = self.store.collect_worker(aid, "taro")
        self.assertEqual(farm["inventory"]["food"], 22)  # 10 + 12

    def test_encounter_not_duplicated(self):
        aid = self.account["id"]
        for i in range(5):
            self.store.record("算数", 1, "calc_add", f"1+{i}", True, "2", "2", aid)
        first = self.store.check_worker_encounters(aid, correct=True, streak=5)
        second = self.store.check_worker_encounters(aid, correct=True, streak=5)
        first_keys = [e["worker_key"] for e in first]
        second_keys = [e["worker_key"] for e in second]
        self.assertIn("taro", first_keys)
        self.assertNotIn("taro", second_keys)

    def test_hire_requires_meeting(self):
        aid = self.account["id"]
        with self.assertRaises(ValueError):
            self.store.hire_worker(aid, "taro")


class FarmTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ProgressStore(os.path.join(self.tmp.name, "farm.sqlite3"))
        self.account = self.store.create_account("のうじょう", "1234")
        self.store.add_points(self.account["id"], "テスト", 1000)

    def tearDown(self):
        self.tmp.cleanup()

    def _db_path(self):
        return self.store.path

    def _set_plot_time(self, plot, seconds_ago):
        import sqlite3
        from datetime import datetime, timedelta
        moment = (datetime.now() - timedelta(seconds=seconds_ago)).isoformat(timespec="seconds")
        with sqlite3.connect(self._db_path()) as conn:
            conn.execute(
                "UPDATE farm_plots SET planted_at = ? WHERE account_id = ? AND plot_index = ?",
                (moment, self.account["id"], plot),
            )

    def _set_animal_ready(self, seconds_ago=999):
        import sqlite3
        from datetime import datetime, timedelta
        moment = (datetime.now() - timedelta(seconds=seconds_ago)).isoformat(timespec="seconds")
        with sqlite3.connect(self._db_path()) as conn:
            conn.execute("UPDATE farm_animals SET ready_at = ? WHERE account_id = ?", (moment, self.account["id"]))

    def _set_gather_ready(self, spot, seconds_ago=999):
        import sqlite3
        from datetime import datetime, timedelta
        moment = (datetime.now() - timedelta(seconds=seconds_ago)).isoformat(timespec="seconds")
        with sqlite3.connect(self._db_path()) as conn:
            conn.execute(
                "INSERT INTO farm_gathers (account_id, spot, ready_at) VALUES (?, ?, ?) "
                "ON CONFLICT(account_id, spot) DO UPDATE SET ready_at = excluded.ready_at",
                (self.account["id"], spot, moment),
            )

    def test_plant_and_harvest_gives_food(self):
        account_id = self.account["id"]
        data = self.store.plant(account_id, 0, "cabbage")
        self.assertEqual(data["account"]["wallet"], 990)
        self.assertEqual(data["plots"][0]["crop"], "cabbage")
        self.assertFalse(data["plots"][0]["ready"])

        self._set_plot_time(0, 60)
        data = self.store.harvest(account_id, 0)
        # お金(ポイント)は勉強で貯める。収穫は食料を増やす
        self.assertEqual(data["account"]["wallet"], 990)
        self.assertEqual(data["account"]["total_points"], 1000)
        self.assertEqual(data["inventory"]["food"], 8)
        self.assertIsNone(data["plots"][0]["crop"])

    def test_animal_buy_and_collect_gives_food(self):
        account_id = self.account["id"]
        data = self.store.buy_animal(account_id, "chicken")
        self.assertEqual(data["account"]["wallet"], 920)
        self.assertEqual(len(data["animals"]), 1)
        animal = data["animals"][0]
        self.assertTrue(animal["nickname"])
        self.assertIn(animal["personality"], {"genki", "otonashii", "kuishinbo", "nonbiri", "nakayoshi"})
        self.assertEqual(animal["bond"], 0)

        self._set_animal_ready()
        data = self.store.collect_animal(account_id, data["animals"][0]["id"])
        self.assertEqual(data["account"]["wallet"], 920)
        self.assertIn("event", data)
        bonus = data["event"]["bonus_yield"]
        self.assertGreaterEqual(data["inventory"]["food"], 10)
        self.assertEqual(data["inventory"]["food"], 10 + bonus)
        collected = data["animals"][0]
        self.assertGreaterEqual(collected["bond"], 1)
        self.assertTrue(collected["last_event"])

    def test_gather_materials(self):
        account_id = self.account["id"]
        data = self.store.gather(account_id, "forest")
        self.assertEqual(data["inventory"]["wood"], 6)
        with self.assertRaises(ValueError):
            self.store.gather(account_id, "forest")
        self._set_gather_ready("forest")
        data = self.store.gather(account_id, "forest")
        self.assertEqual(data["inventory"]["wood"], 12)

        self._set_gather_ready("coal_mine")
        self._set_gather_ready("iron_mine")
        data = self.store.gather(account_id, "coal_mine")
        data = self.store.gather(account_id, "iron_mine")
        self.assertEqual(data["inventory"]["coal"], 4)
        self.assertEqual(data["inventory"]["iron"], 3)

    def test_expand_and_insufficient_points(self):
        account_id = self.account["id"]
        data = self.store.expand_farm(account_id)
        self.assertEqual(data["farm"]["unlocked_plots"], 12)
        self.assertEqual(data["account"]["wallet"], 850)

        poor = self.store.create_account("びんぼう", "1234")
        with self.assertRaises(ValueError):
            self.store.plant(poor["id"], 0, "cabbage")


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import study_app.main as main
        cls._tmp = tempfile.TemporaryDirectory()
        main.store = ProgressStore(os.path.join(cls._tmp.name, "test.sqlite3"))
        cls.main = main

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _new_account(self, nickname="テスト"):
        from study_app.models import AccountCreate
        return self.main.create_account(AccountCreate(nickname=nickname, pin="1234"))

    def test_account_endpoints(self):
        from study_app.models import LoginRequest
        account = self._new_account("あかり")
        self.assertEqual(self.main.get_account(account["id"])["nickname"], "あかり")
        logged = self.main.login(account["id"], LoginRequest(pin="1234"))
        self.assertEqual(logged["id"], account["id"])
        self.assertTrue(self.main.get_account_progress(account["id"])["account"])

    def test_quiz_answer_points_flow(self):
        from study_app.models import AnswerRequest, QuizRequest
        account = self._new_account("ポイント")
        created = self.main.create_quiz(QuizRequest(
            grade=2, subject="math", topics=["multiplication"], count=3, account_id=account["id"]
        ))
        self.assertEqual(created["total"], 3)
        first = created["questions"][0]
        result = self.main.answer(created["quiz_id"], AnswerRequest(question_id=first["id"], answer="0"))
        self.assertIn("correct", result)
        self.assertGreaterEqual(result["earned"], 2)
        self.assertGreater(result["account"]["total_points"], 0)
        self.assertEqual(self.main.quiz_result(created["quiz_id"])["answered"], 1)
        self.assertEqual(self.main.get_progress(account["id"])["summary"]["total"], 1)

        duplicate = self.main.answer(created["quiz_id"], AnswerRequest(question_id=first["id"], answer="0"))
        self.assertEqual(duplicate["earned"], 0)

    def test_wrong_pin_on_login(self):
        from fastapi import HTTPException
        from study_app.models import LoginRequest
        account = self._new_account("PIN確認")
        with self.assertRaises(HTTPException):
            self.main.login(account["id"], LoginRequest(pin="9999"))

    def test_farm_endpoints(self):
        from fastapi import HTTPException
        from study_app.models import (
            FarmAccountRequest, FarmAnimalBuyRequest, FarmBuildingRequest,
            FarmCollectRequest, FarmGatherRequest, FarmHarvestRequest, FarmPlantRequest,
        )
        account = self._new_account("農場API")
        account_id = account["id"]
        self.main.store.add_points(account_id, "テスト", 2000)
        starting_wallet = self.main.store.get_account(account_id)["wallet"]

        data = self.main.get_farm(account_id)
        self.assertEqual(data["farm"]["unlocked_plots"], 9)
        self.assertEqual(len(data["catalog"]["crops"]), 4)
        self.assertIn("food", data["inventory"])
        self.assertEqual(len(data["gathers"]), 4)

        data = self.main.farm_plant(FarmPlantRequest(account_id=account_id, plot=0, crop="cabbage"))
        self.assertEqual(data["plots"][0]["crop"], "cabbage")
        with self.assertRaises(HTTPException):  # 育つ前は収穫できない
            self.main.farm_harvest(FarmHarvestRequest(account_id=account_id, plot=0))

        data = self.main.farm_buy_animal(FarmAnimalBuyRequest(account_id=account_id, animal="chicken"))
        self.assertEqual(len(data["animals"]), 1)
        with self.assertRaises(HTTPException):  # まだ産んでいない
            self.main.farm_collect_animal(FarmCollectRequest(account_id=account_id, animal_id=data["animals"][0]["id"]))

        data = self.main.farm_buy_building(FarmBuildingRequest(account_id=account_id, building="barn"))
        self.assertEqual(data["buildings"][0]["count"], 1)
        data = self.main.farm_buy_building(FarmBuildingRequest(account_id=account_id, building="barn"))
        self.assertEqual(data["buildings"][0]["count"], 2)

        data = self.main.farm_expand(FarmAccountRequest(account_id=account_id))
        self.assertEqual(data["farm"]["unlocked_plots"], 12)
        self.assertEqual(data["account"]["wallet"], starting_wallet - (10 + 80 + 200 * 2 + 150))

        # 採集: 資材は農場内で貯める
        data = self.main.farm_gather(FarmGatherRequest(account_id=account_id, spot="forest"))
        self.assertEqual(data["inventory"]["wood"], 6)
        with self.assertRaises(HTTPException):
            self.main.farm_gather(FarmGatherRequest(account_id=account_id, spot="forest"))

        poor = self._new_account("農場びんぼう")
        with self.assertRaises(HTTPException):
            self.main.farm_plant(FarmPlantRequest(account_id=poor["id"], plot=0, crop="cabbage"))

    def test_worker_encounter_hire_collect_api(self):
        from study_app.models import AnswerRequest, FarmCollectWorkerRequest, FarmHireWorkerRequest, QuizRequest
        account = self._new_account("働き手")
        aid = account["id"]
        self.main.store.add_points(aid, "テスト", 1000)

        # 出会い: streak 5
        created = self.main.create_quiz(QuizRequest(
            grade=1, subject="math", topics=["calc_add"], count=5, account_id=aid
        ))
        encountered = []
        for q in created["questions"]:
            # 正解を送る
            from study_app.generator.base import answers_match
            # find correct answer by trying to answer via store? easier: get quiz internal
            quiz = self.main._get_quiz(created["quiz_id"])
            correct_ans = quiz["questions"][q["id"]].answer
            res = self.main.answer(created["quiz_id"], AnswerRequest(question_id=q["id"], answer=correct_ans))
            encountered.extend(res.get("encounters", []))
        self.assertTrue(any(e["worker_key"] == "taro" for e in encountered))

        # 食料を付与して雇用
        import sqlite3
        with sqlite3.connect(self.main.store.path) as conn:
            conn.execute(
                "INSERT INTO farm_inventory (account_id, resource, amount) VALUES (?, 'food', 20) "
                "ON CONFLICT(account_id, resource) DO UPDATE SET amount = amount + 20",
                (aid,),
            )
        data = self.main.farm_hire_worker(FarmHireWorkerRequest(account_id=aid, worker_key="taro"))
        taro = next(w for w in data["workers"] if w["key"] == "taro")
        self.assertTrue(taro["hired"])

        # 時間を進めて収穫
        from datetime import datetime, timedelta
        moment = (datetime.now() - timedelta(seconds=999)).isoformat(timespec="seconds")
        with sqlite3.connect(self.main.store.path) as conn:
            conn.execute(
                "UPDATE farm_workers SET ready_at = ? WHERE account_id = ? AND worker_key = ?",
                (moment, aid, "taro"),
            )
        data = self.main.farm_collect_worker(FarmCollectWorkerRequest(account_id=aid, worker_key="taro"))
        self.assertGreaterEqual(data["inventory"]["food"], 22)


if __name__ == "__main__":
    unittest.main()

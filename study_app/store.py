"""学習記録・アカウント・ポイントのローカル保存（SQLite）。

外部への送信は行わない。PIN は salt 付き PBKDF2 でハッシュ保存する。
"""
from __future__ import annotations

import hashlib
import hmac
import random
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from . import farm as farm_catalog


def _hash_pin(pin: str):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(salt), 100_000).hex()
    return salt, digest


def _pin_matches(pin: str, salt: Optional[str], digest: Optional[str]) -> bool:
    if not salt or not digest:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(salt), 100_000).hex()
    return hmac.compare_digest(candidate, digest)


def level_title(level: int) -> str:
    if level < 3:
        return "ひよこ"
    if level < 6:
        return "うさぎ"
    if level < 11:
        return "きつね"
    return "ライオン"


class ProgressStore:
    def __init__(self, path):
        self.path = str(path)
        self.lock = threading.Lock()
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS answers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    subject TEXT NOT NULL,
                    grade INTEGER NOT NULL,
                    topic TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    correct INTEGER NOT NULL,
                    given_answer TEXT NOT NULL,
                    correct_answer TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nickname TEXT NOT NULL UNIQUE,
                    pin_salt TEXT,
                    pin_hash TEXT,
                    total_points INTEGER NOT NULL DEFAULT 0,
                    streak INTEGER NOT NULL DEFAULT 0,
                    best_streak INTEGER NOT NULL DEFAULT 0,
                    last_login TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS point_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    reason TEXT NOT NULL,
                    amount INTEGER NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS farm_state (
                    account_id INTEGER PRIMARY KEY,
                    exp INTEGER NOT NULL DEFAULT 0,
                    unlocked_plots INTEGER NOT NULL DEFAULT 9,
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS farm_plots (
                    account_id INTEGER NOT NULL,
                    plot_index INTEGER NOT NULL,
                    crop TEXT,
                    planted_at TEXT,
                    PRIMARY KEY (account_id, plot_index)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS farm_animals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL,
                    animal TEXT NOT NULL,
                    ready_at TEXT NOT NULL,
                    nickname TEXT,
                    personality TEXT,
                    bond INTEGER NOT NULL DEFAULT 0,
                    last_event TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS farm_buildings (
                    account_id INTEGER NOT NULL,
                    building TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (account_id, building)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS farm_inventory (
                    account_id INTEGER NOT NULL,
                    resource TEXT NOT NULL,
                    amount INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (account_id, resource)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS farm_gathers (
                    account_id INTEGER NOT NULL,
                    spot TEXT NOT NULL,
                    ready_at TEXT NOT NULL,
                    PRIMARY KEY (account_id, spot)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mission_claims (
                    account_id INTEGER NOT NULL,
                    mission_date TEXT NOT NULL,
                    mission_key TEXT NOT NULL,
                    claimed_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    PRIMARY KEY (account_id, mission_date, mission_key)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS farm_workers (
                    account_id INTEGER NOT NULL,
                    worker_key TEXT NOT NULL,
                    hired INTEGER NOT NULL DEFAULT 0,
                    met_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    hired_at TEXT,
                    ready_at TEXT,
                    PRIMARY KEY (account_id, worker_key)
                )
            """)

            # 既存DBからの移行
            columns = [row[1] for row in conn.execute("PRAGMA table_info(answers)")]
            if "account_id" not in columns:
                conn.execute("ALTER TABLE answers ADD COLUMN account_id INTEGER")
            account_columns = [row[1] for row in conn.execute("PRAGMA table_info(accounts)")]
            if "wallet" not in account_columns:
                conn.execute("ALTER TABLE accounts ADD COLUMN wallet INTEGER NOT NULL DEFAULT 0")
                conn.execute("UPDATE accounts SET wallet = total_points")

            animal_columns = [row[1] for row in conn.execute("PRAGMA table_info(farm_animals)")]
            if "nickname" not in animal_columns:
                conn.execute("ALTER TABLE farm_animals ADD COLUMN nickname TEXT")
                conn.execute("ALTER TABLE farm_animals ADD COLUMN personality TEXT")
                conn.execute("ALTER TABLE farm_animals ADD COLUMN bond INTEGER NOT NULL DEFAULT 0")
                conn.execute("ALTER TABLE farm_animals ADD COLUMN last_event TEXT")

            count = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
            if count == 0:
                cursor = conn.execute(
                    "INSERT INTO accounts (nickname, pin_salt, pin_hash, wallet) VALUES (?, NULL, NULL, 0)", ("ゲスト",)
                )
                guest_id = cursor.lastrowid
                conn.execute("UPDATE answers SET account_id = ? WHERE account_id IS NULL", (guest_id,))

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, check_same_thread=False)

    # ---------------- アカウント ----------------
    def _account_dict(self, row) -> Dict[str, Any]:
        points = row["total_points"]
        level = points // 100 + 1
        return {
            "id": row["id"],
            "nickname": row["nickname"],
            "total_points": points,
            "wallet": row["wallet"] if "wallet" in row.keys() else points,
            "level": level,
            "level_progress": points % 100,
            "level_title": level_title(level),
            "streak": row["streak"],
            "best_streak": row["best_streak"],
            "has_pin": bool(row["pin_hash"]),
            "created_at": row["created_at"],
        }

    def list_accounts(self) -> List[Dict[str, Any]]:
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM accounts ORDER BY id").fetchall()
        return [self._account_dict(row) for row in rows]

    def get_account(self, account_id: int) -> Optional[Dict[str, Any]]:
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return self._account_dict(row) if row else None

    def create_account(self, nickname: str, pin: Optional[str] = None) -> Dict[str, Any]:
        if pin:
            salt, digest = _hash_pin(pin)
        else:
            salt, digest = None, None
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "INSERT INTO accounts (nickname, pin_salt, pin_hash, wallet) VALUES (?, ?, ?, 0)",
                (nickname, salt, digest),
            )
            account_id = cursor.lastrowid
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return self._account_dict(row)

    def set_pin(self, account_id: int, pin: str) -> None:
        salt, digest = _hash_pin(pin)
        with self.lock, self._connect() as conn:
            conn.execute("UPDATE accounts SET pin_salt = ?, pin_hash = ? WHERE id = ?", (salt, digest, account_id))

    def login(self, account_id: int, pin: Optional[str] = None, trusted: bool = False) -> Dict[str, Any]:
        """PIN を確認し、1日1回のログインボーナスを与える。"""
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
            if not row:
                raise LookupError("アカウントが見つかりません")
            if row["pin_hash"] and not trusted:
                if pin is None or not _pin_matches(pin, row["pin_salt"], row["pin_hash"]):
                    raise PermissionError("PIN がちがいます")
            today = datetime.now().strftime("%Y-%m-%d")
            if (row["last_login"] or "")[:10] != today:
                conn.execute("UPDATE accounts SET last_login = ? WHERE id = ?", (today, account_id))
                conn.execute(
                    "INSERT INTO point_events (account_id, reason, amount) VALUES (?, 'デイリーボーナス', 5)",
                    (account_id,),
                )
                conn.execute(
                    "UPDATE accounts SET total_points = total_points + 5, wallet = wallet + 5 WHERE id = ?",
                    (account_id,),
                )
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return self._account_dict(row)

    def delete_account(self, account_id: int, pin: Optional[str] = None, trusted: bool = False) -> None:
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
            if not row:
                raise LookupError("アカウントが見つかりません")
            if conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] <= 1:
                raise ValueError("最後のアカウントは消せません")
            if row["pin_hash"] and not trusted:
                if pin is None or not _pin_matches(pin, row["pin_salt"], row["pin_hash"]):
                    raise PermissionError("PIN がちがいます")
            conn.execute("DELETE FROM answers WHERE account_id = ?", (account_id,))
            conn.execute("DELETE FROM point_events WHERE account_id = ?", (account_id,))
            conn.execute("DELETE FROM farm_plots WHERE account_id = ?", (account_id,))
            conn.execute("DELETE FROM farm_animals WHERE account_id = ?", (account_id,))
            conn.execute("DELETE FROM farm_buildings WHERE account_id = ?", (account_id,))
            conn.execute("DELETE FROM farm_inventory WHERE account_id = ?", (account_id,))
            conn.execute("DELETE FROM farm_gathers WHERE account_id = ?", (account_id,))
            conn.execute("DELETE FROM mission_claims WHERE account_id = ?", (account_id,))
            conn.execute("DELETE FROM farm_workers WHERE account_id = ?", (account_id,))
            conn.execute("DELETE FROM farm_state WHERE account_id = ?", (account_id,))
            conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))

    # ---------------- 記録・ポイント ----------------
    def record(self, subject: str, grade: int, topic: str, prompt: str,
               correct: bool, given: str, correct_answer: str, account_id: int) -> None:
        with self.lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO answers (account_id, subject, grade, topic, prompt, correct, given_answer, correct_answer) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (account_id, subject, grade, topic, prompt, int(correct), str(given), str(correct_answer)),
            )

    def add_points(self, account_id: int, reason: str, amount: int) -> None:
        with self.lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO point_events (account_id, reason, amount) VALUES (?, ?, ?)",
                (account_id, reason, amount),
            )
            conn.execute(
                "UPDATE accounts SET total_points = total_points + ?, wallet = wallet + ? WHERE id = ?",
                (amount, amount, account_id),
            )

    def set_streak(self, account_id: int, streak: int) -> None:
        with self.lock, self._connect() as conn:
            conn.execute(
                "UPDATE accounts SET streak = ?, best_streak = MAX(best_streak, ?) WHERE id = ?",
                (streak, streak, account_id),
            )

    def summary(self, account_id: Optional[int] = None, limit: int = 8) -> Dict[str, Any]:
        where = " WHERE account_id = ?" if account_id is not None else ""
        params = (account_id,) if account_id is not None else ()
        with self.lock, self._connect() as conn:
            total, ok = conn.execute(
                f"SELECT COUNT(*), COALESCE(SUM(correct), 0) FROM answers{where}", params
            ).fetchone()
            by_subject = [
                {"subject": row[0], "total": row[1], "correct": row[2]}
                for row in conn.execute(
                    f"SELECT subject, COUNT(*), SUM(correct) FROM answers{where} GROUP BY subject ORDER BY subject",
                    params,
                )
            ]
            weak = [
                {"topic": row[0], "total": row[1], "correct": row[2]}
                for row in conn.execute(
                    f"SELECT topic, COUNT(*), SUM(correct) FROM answers{where} GROUP BY topic "
                    "ORDER BY (1.0 * SUM(correct) / COUNT(*)) ASC, COUNT(*) DESC LIMIT 5",
                    params,
                )
            ]
            conditions = ["correct = 0"]
            wrong_params: List[Any] = []
            if account_id is not None:
                conditions.insert(0, "account_id = ?")
                wrong_params.append(account_id)
            wrong_params.append(limit)
            recent_wrong = [
                {"subject": row[0], "prompt": row[1], "given": row[2], "correct_answer": row[3],
                 "created_at": row[4]}
                for row in conn.execute(
                    "SELECT subject, prompt, given_answer, correct_answer, created_at FROM answers "
                    f"WHERE {' AND '.join(conditions)} ORDER BY id DESC LIMIT ?",
                    wrong_params,
                )
            ]
        return {
            "total": total,
            "correct": ok,
            "accuracy": round(ok / total * 100, 1) if total else 0.0,
            "by_subject": by_subject,
            "weak_topics": weak,
            "recent_wrong": recent_wrong,
        }

    def account_progress(self, account_id: int) -> Dict[str, Any]:
        account = self.get_account(account_id)
        if not account:
            raise LookupError("アカウントが見つかりません")
        with self.lock, self._connect() as conn:
            breakdown = [
                {"reason": row[0], "amount": row[1]}
                for row in conn.execute(
                    "SELECT reason, SUM(amount) FROM point_events WHERE account_id = ? GROUP BY reason ORDER BY SUM(amount) DESC",
                    (account_id,),
                )
            ]
            events = [
                {"reason": row[0], "amount": row[1], "created_at": row[2]}
                for row in conn.execute(
                    "SELECT reason, amount, created_at FROM point_events WHERE account_id = ? ORDER BY id DESC LIMIT 8",
                    (account_id,),
                )
            ]
        return {
            "account": account,
            "summary": self.summary(account_id),
            "point_breakdown": breakdown,
            "recent_events": events,
        }

    # ---------------- 分析・ミッション ----------------
    def weak_topics(self, account_id: int, subject: Optional[str] = None, grade: Optional[int] = None, limit: int = 5) -> List[Dict[str, Any]]:
        conditions = ["account_id = ?"]
        params: List[Any] = [account_id]
        if subject:
            conditions.append("subject = ?")
            params.append(subject)
        if grade is not None:
            conditions.append("grade = ?")
            params.append(grade)
        params.append(limit)
        with self.lock, self._connect() as conn:
            rows = conn.execute(
                f"SELECT topic, subject, grade, COUNT(*) AS total, SUM(correct) AS correct "
                f"FROM answers WHERE {' AND '.join(conditions)} "
                "GROUP BY topic, subject, grade "
                "HAVING COUNT(*) >= 1 "
                "ORDER BY (1.0 * SUM(correct) / COUNT(*)) ASC, COUNT(*) DESC LIMIT ?",
                params,
            ).fetchall()
        items = []
        for topic, subj, grd, total, correct in rows:
            accuracy = round(correct / total * 100, 1) if total else 0.0
            items.append({
                "topic": topic, "subject": subj, "grade": grd,
                "total": total, "correct": correct, "accuracy": accuracy,
            })
        return items

    def analysis(self, account_id: int) -> Dict[str, Any]:
        account = self.get_account(account_id)
        if not account:
            raise LookupError("アカウントが見つかりません")
        summary = self.summary(account_id)
        weak = self.weak_topics(account_id, limit=5)
        today = datetime.now().strftime("%Y-%m-%d")
        with self.lock, self._connect() as conn:
            today_total, today_correct = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(correct),0) FROM answers WHERE account_id = ? AND date(created_at)=date(?)",
                (account_id, today),
            ).fetchone()
            by_topic = [
                {"topic": row[0], "subject": row[1], "total": row[2], "correct": row[3],
                 "accuracy": round(row[3] / row[2] * 100, 1) if row[2] else 0.0}
                for row in conn.execute(
                    "SELECT topic, subject, COUNT(*), SUM(correct) FROM answers WHERE account_id = ? "
                    "GROUP BY topic, subject ORDER BY (1.0*SUM(correct)/COUNT(*)) ASC, COUNT(*) DESC LIMIT 8",
                    (account_id,),
                ).fetchall()
            ]
        missions = self._missions_status(account_id, today, today_total, today_correct)
        return {
            "account": account,
            "summary": summary,
            "weak_topics": weak,
            "topic_accuracy": by_topic,
            "today": {"answered": today_total, "correct": today_correct},
            "missions": missions,
            "recommended_mode": "adaptive" if weak else "normal",
        }

    def _mission_templates(self) -> List[Dict[str, Any]]:
        return [
            {"key": "daily_answer_5", "title": "5問チャレンジ", "description": "きょう 5問 とこう",
             "type": "answered", "goal": 5, "reward_points": 20, "reward_resources": {"food": 3}},
            {"key": "daily_correct_3", "title": "3問せいかい", "description": "きょう 3問 せいかいしよう",
             "type": "correct", "goal": 3, "reward_points": 15, "reward_resources": {"wood": 2}},
            {"key": "daily_answer_10", "title": "10問マスター", "description": "きょう 10問 といて 牧場を応援",
             "type": "answered", "goal": 10, "reward_points": 30, "reward_resources": {"stone": 2, "food": 2}},
        ]

    def _missions_status(self, account_id: int, today: str, today_total: int, today_correct: int) -> List[Dict[str, Any]]:
        with self.lock, self._connect() as conn:
            claimed = {
                row[0]
                for row in conn.execute(
                    "SELECT mission_key FROM mission_claims WHERE account_id = ? AND mission_date = ?",
                    (account_id, today),
                ).fetchall()
            }
        missions = []
        for tpl in self._mission_templates():
            progress = today_correct if tpl["type"] == "correct" else today_total
            done = progress >= tpl["goal"]
            missions.append({
                **tpl,
                "progress": min(progress, tpl["goal"]),
                "done": done,
                "claimed": tpl["key"] in claimed,
            })
        return missions

    def claim_mission(self, account_id: int, mission_key: str) -> Dict[str, Any]:
        account = self.get_account(account_id)
        if not account:
            raise LookupError("アカウントが見つかりません")
        today = datetime.now().strftime("%Y-%m-%d")
        with self.lock, self._connect() as conn:
            today_total, today_correct = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(correct),0) FROM answers WHERE account_id = ? AND date(created_at)=date(?)",
                (account_id, today),
            ).fetchone()
        missions = self._missions_status(account_id, today, today_total, today_correct)
        mission = next((m for m in missions if m["key"] == mission_key), None)
        if not mission:
            raise ValueError("ミッションが見つかりません")
        if not mission["done"]:
            raise ValueError("まだ ミッション達成していません")
        if mission["claimed"]:
            raise ValueError("このミッションは もう受け取りました")

        with self.lock, self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO mission_claims (account_id, mission_date, mission_key) VALUES (?, ?, ?)",
                (account_id, today, mission_key),
            )
            inserted = conn.execute(
                "SELECT changes()"
            ).fetchone()[0]
            for resource, amount in mission.get("reward_resources", {}).items():
                self._add_resource(conn, account_id, resource, amount)
        if not inserted:
            # already claimed in race; treat as already claimed
            raise ValueError("このミッションは もう受け取りました")
        self.add_points(account_id, f"ミッション:{mission['title']}", mission["reward_points"])
        return self.analysis(account_id)

    def check_worker_encounters(self, account_id: int, correct: bool, streak: int) -> List[Dict[str, Any]]:
        with self.lock, self._connect() as conn:
            met_keys = {
                row[0] for row in conn.execute(
                    "SELECT worker_key FROM farm_workers WHERE account_id = ?", (account_id,)
                ).fetchall()
            }
            total_answered, total_correct = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(correct),0) FROM answers WHERE account_id = ?",
                (account_id,),
            ).fetchone()

        newly_met = []
        rng = random.Random()
        for key, worker in farm_catalog.WORKER_CANDIDATES.items():
            if key in met_keys:
                continue
            encounter = worker.get("encounter", {})
            etype = encounter.get("type")
            matched = False
            if etype == "correct_streak" and correct and streak >= encounter.get("value", 999):
                matched = True
            elif etype == "total_correct" and total_correct >= encounter.get("value", 999999):
                matched = True
            elif etype == "total_answered" and total_answered >= encounter.get("value", 999999):
                matched = True
            elif etype == "random_correct" and correct and rng.random() < encounter.get("chance", 0):
                matched = True
            if not matched:
                continue
            with self.lock, self._connect() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO farm_workers (account_id, worker_key, hired, met_at) VALUES (?, ?, 0, datetime('now','localtime'))",
                    (account_id, key),
                )
                inserted = conn.execute("SELECT changes()").fetchone()[0]
            if inserted:
                newly_met.append({
                    "worker_key": key,
                    "name": worker["name"],
                    "emoji": worker["emoji"],
                    "role": worker["role"],
                    "description": worker["description"],
                    "message": encounter.get("text", f"{worker['name']} と出会った！"),
                })
        return newly_met

    # ---------------- 農場ゲーム ----------------
    def _ensure_farm_state(self, conn, account_id: int) -> None:
        conn.execute("INSERT OR IGNORE INTO farm_state (account_id) VALUES (?)", (account_id,))

    def _spend(self, conn, account_id: int, cost: int) -> None:
        row = conn.execute("SELECT wallet FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if not row:
            raise LookupError("アカウントが見つかりません")
        if row["wallet"] < cost:
            raise ValueError(f"ポイントが 足りません（必要: {cost} pt）")
        conn.execute("UPDATE accounts SET wallet = wallet - ? WHERE id = ?", (cost, account_id))

    def _add_resource(self, conn, account_id: int, resource: str, amount: int) -> None:
        conn.execute(
            "INSERT INTO farm_inventory (account_id, resource, amount) VALUES (?, ?, ?) "
            "ON CONFLICT(account_id, resource) DO UPDATE SET amount = amount + excluded.amount",
            (account_id, resource, amount),
        )

    def _inventory(self, conn, account_id: int) -> Dict[str, int]:
        rows = conn.execute(
            "SELECT resource, amount FROM farm_inventory WHERE account_id = ?", (account_id,)
        ).fetchall()
        inv = {key: 0 for key in farm_catalog.RESOURCE_META}
        for row in rows:
            inv[row["resource"]] = row["amount"]
        return inv

    def get_farm(self, account_id: int) -> Dict[str, Any]:
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            self._ensure_farm_state(conn, account_id)
            state = conn.execute("SELECT * FROM farm_state WHERE account_id = ?", (account_id,)).fetchone()
            plot_rows = {
                row["plot_index"]: row
                for row in conn.execute("SELECT * FROM farm_plots WHERE account_id = ?", (account_id,))
            }
            animal_rows = conn.execute(
                "SELECT * FROM farm_animals WHERE account_id = ? ORDER BY id", (account_id,)
            ).fetchall()
            building_rows = conn.execute(
                "SELECT * FROM farm_buildings WHERE account_id = ? ORDER BY building", (account_id,)
            ).fetchall()
            gather_rows = {
                row["spot"]: row
                for row in conn.execute("SELECT * FROM farm_gathers WHERE account_id = ?", (account_id,))
            }
            worker_rows = {
                row["worker_key"]: row
                for row in conn.execute("SELECT * FROM farm_workers WHERE account_id = ?", (account_id,))
            }
            inventory = self._inventory(conn, account_id)

        unlocked = state["unlocked_plots"]
        plots = []
        for index in range(farm_catalog.MAX_PLOTS):
            if index >= unlocked:
                plots.append({"index": index, "unlocked": False})
                continue
            row = plot_rows.get(index)
            crop_key = row["crop"] if row else None
            if crop_key in farm_catalog.CROPS:
                crop = farm_catalog.CROPS[crop_key]
                info = farm_catalog.growth_info(row["planted_at"], crop["grow"])
                plots.append({
                    "index": index, "unlocked": True, "crop": crop_key,
                    "name": crop["name"], "emoji": crop["emoji"],
                    "yield": crop["yield"], "resource": crop["resource"], **info,
                })
            else:
                plots.append({"index": index, "unlocked": True, "crop": None})

        animals = []
        for row in animal_rows:
            animal = farm_catalog.ANIMALS.get(row["animal"])
            if not animal:
                continue
            remaining = farm_catalog.remaining_seconds(row["ready_at"])
            personality_key = row["personality"] if "personality" in row.keys() and row["personality"] else "genki"
            personality = farm_catalog.ANIMAL_PERSONALITIES.get(personality_key, farm_catalog.ANIMAL_PERSONALITIES["genki"])
            nickname = row["nickname"] if "nickname" in row.keys() and row["nickname"] else animal["name"]
            bond = row["bond"] if "bond" in row.keys() and row["bond"] is not None else 0
            last_event = row["last_event"] if "last_event" in row.keys() else None
            animals.append({
                "id": row["id"], "key": row["animal"], "name": animal["name"], "emoji": animal["emoji"],
                "product": animal["product"], "product_emoji": animal["product_emoji"],
                "yield": animal["yield"], "resource": animal["resource"],
                "ready": remaining == 0, "remaining": remaining,
                "nickname": nickname, "personality": personality_key,
                "personality_name": personality["name"], "personality_emoji": personality["emoji"],
                "personality_description": personality["description"],
                "bond": bond, "last_event": last_event,
            })

        buildings = []
        for row in building_rows:
            building = farm_catalog.BUILDINGS.get(row["building"])
            if not building:
                continue
            buildings.append({
                "key": row["building"], "name": building["name"], "emoji": building["emoji"],
                "count": row["count"], "description": building["description"],
            })

        gathers = []
        for key, spot in farm_catalog.GATHER_SPOTS.items():
            row = gather_rows.get(key)
            ready_at = row["ready_at"] if row else farm_catalog.now_iso()
            remaining = farm_catalog.remaining_seconds(ready_at)
            gathers.append({
                "key": key, "name": spot["name"], "emoji": spot["emoji"],
                "resource": spot["resource"], "resource_name": spot["resource_name"],
                "yield": spot["yield"], "interval": spot["interval"],
                "description": spot["description"],
                "ready": remaining == 0, "remaining": remaining,
            })

        workers = []
        for key, worker in farm_catalog.WORKER_CANDIDATES.items():
            row = worker_rows.get(key)
            if not row:
                continue
            hired = bool(row["hired"])
            ready_at = row["ready_at"] if "ready_at" in row.keys() else None
            remaining = farm_catalog.remaining_seconds(ready_at) if hired and ready_at else 0
            workers.append({
                "key": key,
                "name": worker["name"],
                "emoji": worker["emoji"],
                "role": worker["role"],
                "description": worker["description"],
                "hire_cost": worker["hire_cost"],
                "work_interval": worker["work_interval"],
                "yield": worker["yield"],
                "hired": hired,
                "met_at": row["met_at"],
                "hired_at": row["hired_at"] if "hired_at" in row.keys() else None,
                "ready": hired and remaining == 0,
                "remaining": remaining if hired else 0,
            })

        level = farm_catalog.farm_level(state["exp"])
        expansion_cost = (
            farm_catalog.PLOT_EXPANSION_COST * ((unlocked - 9) // 3 + 1)
            if unlocked < farm_catalog.MAX_PLOTS else None
        )
        account = self.get_account(account_id)
        return {
            "account": account,
            "farm": {
                "level": level,
                "exp": state["exp"],
                "exp_to_next": 100 - state["exp"] % 100,
                "unlocked_plots": unlocked,
                "max_plots": farm_catalog.MAX_PLOTS,
            },
            "inventory": inventory,
            "plots": plots,
            "animals": animals,
            "buildings": buildings,
            "gathers": gathers,
            "workers": workers,
            "catalog": farm_catalog.catalog(),
            "expansion_cost": expansion_cost,
        }

    def plant(self, account_id: int, plot: int, crop_key: str) -> Dict[str, Any]:
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            self._ensure_farm_state(conn, account_id)
            crop = farm_catalog.CROPS.get(crop_key)
            if not crop:
                raise ValueError("そのたねは ありません")
            state = conn.execute("SELECT unlocked_plots FROM farm_state WHERE account_id = ?", (account_id,)).fetchone()
            if plot < 0 or plot >= state["unlocked_plots"]:
                raise ValueError("この畑は まだ ひらいていません")
            current = conn.execute(
                "SELECT crop FROM farm_plots WHERE account_id = ? AND plot_index = ?", (account_id, plot)
            ).fetchone()
            if current and current["crop"]:
                raise ValueError("この畑には もう 植えてあります")
            self._spend(conn, account_id, crop["cost"])
            conn.execute(
                "INSERT OR REPLACE INTO farm_plots (account_id, plot_index, crop, planted_at) VALUES (?, ?, ?, ?)",
                (account_id, plot, crop_key, farm_catalog.now_iso()),
            )
        return self.get_farm(account_id)

    def harvest(self, account_id: int, plot: int) -> Dict[str, Any]:
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT crop, planted_at FROM farm_plots WHERE account_id = ? AND plot_index = ?",
                (account_id, plot),
            ).fetchone()
            if not row or row["crop"] not in farm_catalog.CROPS:
                raise ValueError("この畑には 何も 植えていません")
            crop = farm_catalog.CROPS[row["crop"]]
            info = farm_catalog.growth_info(row["planted_at"], crop["grow"])
            if not info["ready"]:
                raise ValueError(f"まだ 育っていません（あと {info['remaining']} 秒）")
            self._add_resource(conn, account_id, crop["resource"], crop["yield"])
            conn.execute("UPDATE farm_state SET exp = exp + 5 WHERE account_id = ?", (account_id,))
            conn.execute(
                "DELETE FROM farm_plots WHERE account_id = ? AND plot_index = ?", (account_id, plot)
            )
        return self.get_farm(account_id)

    def buy_animal(self, account_id: int, animal_key: str) -> Dict[str, Any]:
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            animal = farm_catalog.ANIMALS.get(animal_key)
            if not animal:
                raise ValueError("そのどうぶつは いません")
            self._spend(conn, account_id, animal["cost"])
            ready_at = (datetime.now() + timedelta(seconds=animal["interval"])).isoformat(timespec="seconds")
            rng = random.Random()
            existing = {
                row["nickname"]
                for row in conn.execute(
                    "SELECT nickname FROM farm_animals WHERE account_id = ? AND nickname IS NOT NULL",
                    (account_id,),
                ).fetchall()
            }
            nickname = farm_catalog.pick_nickname(rng, existing)
            personality = farm_catalog.pick_personality(rng)
            conn.execute(
                "INSERT INTO farm_animals (account_id, animal, ready_at, nickname, personality, bond, last_event) "
                "VALUES (?, ?, ?, ?, ?, 0, NULL)",
                (account_id, animal_key, ready_at, nickname, personality),
            )
            conn.execute("UPDATE farm_state SET exp = exp + 10 WHERE account_id = ?", (account_id,))
        return self.get_farm(account_id)

    def collect_animal(self, account_id: int, animal_id: int) -> Dict[str, Any]:
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM farm_animals WHERE id = ? AND account_id = ?",
                (animal_id, account_id),
            ).fetchone()
            if not row or row["animal"] not in farm_catalog.ANIMALS:
                raise ValueError("どうぶつが 見つかりません")
            if farm_catalog.remaining_seconds(row["ready_at"]) > 0:
                raise ValueError("まだ とれるものが ありません")
            animal_def = farm_catalog.ANIMALS[row["animal"]]
            personality_key = row["personality"] if "personality" in row.keys() and row["personality"] else "genki"
            nickname = row["nickname"] if "nickname" in row.keys() and row["nickname"] else animal_def["name"]
            bond = row["bond"] if "bond" in row.keys() and row["bond"] is not None else 0
            rng = random.Random()
            event = farm_catalog.roll_animal_event(
                {**animal_def, "nickname": nickname}, personality_key, bond, rng
            )
            total_yield = animal_def["yield"] + event["bonus_yield"]
            new_bond = bond + event["bond_gain"]
            self._add_resource(conn, account_id, animal_def["resource"], total_yield)
            conn.execute("UPDATE farm_state SET exp = exp + 8 WHERE account_id = ?", (account_id,))
            next_at = (datetime.now() + timedelta(seconds=animal_def["interval"])).isoformat(timespec="seconds")
            conn.execute(
                "UPDATE farm_animals SET ready_at = ?, bond = ?, last_event = ? WHERE id = ?",
                (next_at, new_bond, event["message"], animal_id),
            )
        data = self.get_farm(account_id)
        data["event"] = event
        return data

    def gather(self, account_id: int, spot_key: str) -> Dict[str, Any]:
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            self._ensure_farm_state(conn, account_id)
            spot = farm_catalog.GATHER_SPOTS.get(spot_key)
            if not spot:
                raise ValueError("その場所では 集められません")
            row = conn.execute(
                "SELECT ready_at FROM farm_gathers WHERE account_id = ? AND spot = ?",
                (account_id, spot_key),
            ).fetchone()
            ready_at = row["ready_at"] if row else farm_catalog.now_iso()
            if farm_catalog.remaining_seconds(ready_at) > 0:
                remaining = farm_catalog.remaining_seconds(ready_at)
                raise ValueError(f"まだ 集められません（あと {remaining} 秒）")
            self._add_resource(conn, account_id, spot["resource"], spot["yield"])
            next_at = (datetime.now() + timedelta(seconds=spot["interval"])).isoformat(timespec="seconds")
            conn.execute(
                "INSERT INTO farm_gathers (account_id, spot, ready_at) VALUES (?, ?, ?) "
                "ON CONFLICT(account_id, spot) DO UPDATE SET ready_at = excluded.ready_at",
                (account_id, spot_key, next_at),
            )
            conn.execute("UPDATE farm_state SET exp = exp + 5 WHERE account_id = ?", (account_id,))
        return self.get_farm(account_id)

    def buy_building(self, account_id: int, building_key: str) -> Dict[str, Any]:
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            building = farm_catalog.BUILDINGS.get(building_key)
            if not building:
                raise ValueError("そのたてものは ありません")
            self._spend(conn, account_id, building["cost"])
            conn.execute(
                "INSERT INTO farm_buildings (account_id, building, count) VALUES (?, ?, 1) "
                "ON CONFLICT(account_id, building) DO UPDATE SET count = count + 1",
                (account_id, building_key),
            )
            conn.execute("UPDATE farm_state SET exp = exp + 20 WHERE account_id = ?", (account_id,))
        return self.get_farm(account_id)

    def expand_farm(self, account_id: int) -> Dict[str, Any]:
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            self._ensure_farm_state(conn, account_id)
            state = conn.execute("SELECT unlocked_plots FROM farm_state WHERE account_id = ?", (account_id,)).fetchone()
            unlocked = state["unlocked_plots"]
            if unlocked >= farm_catalog.MAX_PLOTS:
                raise ValueError("これ以上 ひろげられません")
            cost = farm_catalog.PLOT_EXPANSION_COST * ((unlocked - 9) // 3 + 1)
            self._spend(conn, account_id, cost)
            conn.execute(
                "UPDATE farm_state SET unlocked_plots = unlocked_plots + 3 WHERE account_id = ?", (account_id,)
            )
            conn.execute("UPDATE farm_state SET exp = exp + 15 WHERE account_id = ?", (account_id,))
        return self.get_farm(account_id)

    def hire_worker(self, account_id: int, worker_key: str) -> Dict[str, Any]:
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            self._ensure_farm_state(conn, account_id)
            worker = farm_catalog.WORKER_CANDIDATES.get(worker_key)
            if not worker:
                raise ValueError("その働き手は いません")
            row = conn.execute(
                "SELECT * FROM farm_workers WHERE account_id = ? AND worker_key = ?",
                (account_id, worker_key),
            ).fetchone()
            if not row:
                raise ValueError("まだ この人には 出会っていません")
            if row["hired"]:
                raise ValueError("この人は もう 雇っています")

            hire_cost = worker.get("hire_cost", {})
            points_cost = int(hire_cost.get("points", 0))
            resource_costs = {k: int(v) for k, v in hire_cost.items() if k != "points" and int(v) > 0}

            if points_cost:
                self._spend(conn, account_id, points_cost)
            if resource_costs:
                inventory = self._inventory(conn, account_id)
                for resource, amount in resource_costs.items():
                    if inventory.get(resource, 0) < amount:
                        name = farm_catalog.RESOURCE_META.get(resource, {}).get("name", resource)
                        raise ValueError(f"{name} が 足りません（必要: {amount}）")
                for resource, amount in resource_costs.items():
                    self._add_resource(conn, account_id, resource, -amount)

            now = datetime.now()
            ready_at = (now + timedelta(seconds=worker["work_interval"])).isoformat(timespec="seconds")
            conn.execute(
                "UPDATE farm_workers SET hired = 1, hired_at = ?, ready_at = ? WHERE account_id = ? AND worker_key = ?",
                (now.isoformat(timespec="seconds"), ready_at, account_id, worker_key),
            )
            conn.execute("UPDATE farm_state SET exp = exp + 15 WHERE account_id = ?", (account_id,))
        data = self.get_farm(account_id)
        data["event"] = {"message": f"{worker['name']} を雇いました！牧場を手伝ってくれます。"}
        return data

    def collect_worker(self, account_id: int, worker_key: str) -> Dict[str, Any]:
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            self._ensure_farm_state(conn, account_id)
            worker = farm_catalog.WORKER_CANDIDATES.get(worker_key)
            if not worker:
                raise ValueError("その働き手は いません")
            row = conn.execute(
                "SELECT * FROM farm_workers WHERE account_id = ? AND worker_key = ?",
                (account_id, worker_key),
            ).fetchone()
            if not row or not row["hired"]:
                raise ValueError("この人は まだ 雇っていません")
            if farm_catalog.remaining_seconds(row["ready_at"]) > 0:
                remaining = farm_catalog.remaining_seconds(row["ready_at"])
                raise ValueError(f"まだ はたらき中です（あと {remaining} 秒）")
            for resource, amount in worker.get("yield", {}).items():
                self._add_resource(conn, account_id, resource, amount)
            next_at = (datetime.now() + timedelta(seconds=worker["work_interval"])).isoformat(timespec="seconds")
            conn.execute(
                "UPDATE farm_workers SET ready_at = ? WHERE account_id = ? AND worker_key = ?",
                (next_at, account_id, worker_key),
            )
            conn.execute("UPDATE farm_state SET exp = exp + 5 WHERE account_id = ?", (account_id,))
        data = self.get_farm(account_id)
        gained = " / ".join(
            f"{farm_catalog.RESOURCE_META.get(r, {}).get('name', r)}+{a}"
            for r, a in worker.get("yield", {}).items()
        )
        data["event"] = {"message": f"{worker['name']} が仕事を終えました！ {gained}"}
        return data

    def clear(self, account_id: Optional[int] = None) -> None:
        with self.lock, self._connect() as conn:
            if account_id is None:
                conn.execute("DELETE FROM answers")
                conn.execute("DELETE FROM point_events")
                conn.execute("DELETE FROM mission_claims")
                conn.execute("DELETE FROM farm_workers")
                conn.execute("DELETE FROM farm_plots")
                conn.execute("DELETE FROM farm_animals")
                conn.execute("DELETE FROM farm_buildings")
                conn.execute("DELETE FROM farm_inventory")
                conn.execute("DELETE FROM farm_gathers")
                conn.execute("DELETE FROM farm_state")
            else:
                conn.execute("DELETE FROM answers WHERE account_id = ?", (account_id,))
                conn.execute("DELETE FROM point_events WHERE account_id = ?", (account_id,))
                conn.execute("DELETE FROM mission_claims WHERE account_id = ?", (account_id,))
                conn.execute("DELETE FROM farm_workers WHERE account_id = ?", (account_id,))
                conn.execute("DELETE FROM farm_plots WHERE account_id = ?", (account_id,))
                conn.execute("DELETE FROM farm_animals WHERE account_id = ?", (account_id,))
                conn.execute("DELETE FROM farm_buildings WHERE account_id = ?", (account_id,))
                conn.execute("DELETE FROM farm_inventory WHERE account_id = ?", (account_id,))
                conn.execute("DELETE FROM farm_gathers WHERE account_id = ?", (account_id,))
                conn.execute("DELETE FROM farm_state WHERE account_id = ?", (account_id,))
                conn.execute(
                    "UPDATE accounts SET total_points = 0, wallet = 0, streak = 0, best_streak = 0 WHERE id = ?",
                    (account_id,),
                )

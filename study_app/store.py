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
                    hunger INTEGER NOT NULL DEFAULT 0,
                    hunger_updated_at TEXT,
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
                    last_event TEXT,
                    fullness INTEGER NOT NULL DEFAULT 0
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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS farm_tools (
                    account_id INTEGER NOT NULL,
                    tool_key TEXT NOT NULL,
                    acquired_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    PRIMARY KEY (account_id, tool_key)
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
            if "fullness" not in animal_columns:
                conn.execute("ALTER TABLE farm_animals ADD COLUMN fullness INTEGER NOT NULL DEFAULT 0")

            farm_state_columns = [row[1] for row in conn.execute("PRAGMA table_info(farm_state)")]
            if "hunger" not in farm_state_columns:
                conn.execute("ALTER TABLE farm_state ADD COLUMN hunger INTEGER NOT NULL DEFAULT 0")
                conn.execute("ALTER TABLE farm_state ADD COLUMN hunger_updated_at TEXT")

            # 旧食料(food)を野菜(vegetable)へ移行
            conn.execute(
                "INSERT INTO farm_inventory (account_id, resource, amount) "
                "SELECT account_id, 'vegetable', amount FROM farm_inventory WHERE resource = 'food' "
                "ON CONFLICT(account_id, resource) DO UPDATE SET amount = amount + excluded.amount"
            )
            conn.execute("DELETE FROM farm_inventory WHERE resource = 'food'")

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
            conn.execute("DELETE FROM farm_tools WHERE account_id = ?", (account_id,))
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
             "type": "answered", "goal": 5, "reward_points": 20, "reward_resources": {"vegetable": 3}},
            {"key": "daily_correct_3", "title": "3問せいかい", "description": "きょう 3問 せいかいしよう",
             "type": "correct", "goal": 3, "reward_points": 15, "reward_resources": {"wood": 2}},
            {"key": "daily_answer_10", "title": "10問マスター", "description": "きょう 10問 といて 牧場を応援",
             "type": "answered", "goal": 10, "reward_points": 30, "reward_resources": {"stone": 2, "fruit": 2}},
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

    def _spend_cost(self, conn, account_id: int, cost: Any) -> None:
        """ポイント+資材の複合コスト、または従来のポイントコストを支払う。"""
        if isinstance(cost, dict):
            points = int(cost.get("points", 0))
            resources = {k: int(v) for k, v in cost.items() if k != "points" and int(v) > 0}
            if points:
                self._spend(conn, account_id, points)
            if resources:
                inv = self._inventory(conn, account_id)
                for resource, amount in resources.items():
                    if inv.get(resource, 0) < amount:
                        name = farm_catalog.RESOURCE_META.get(resource, {}).get("name", resource)
                        raise ValueError(f"{name} が 足りません（必要: {amount}）")
                for resource, amount in resources.items():
                    self._add_resource(conn, account_id, resource, -amount)
            return
        self._spend(conn, account_id, int(cost))

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
            # 主人公の空腹度を時間経過で更新（さぼると赤字）
            hunger = int(state["hunger"] or 0) if "hunger" in state.keys() else 0
            hunger_updated_at = state["hunger_updated_at"] if "hunger_updated_at" in state.keys() else None
            now_dt = datetime.now()
            if hunger_updated_at:
                try:
                    last_dt = datetime.fromisoformat(hunger_updated_at)
                    elapsed = max(0, int((now_dt - last_dt).total_seconds()))
                except Exception:
                    elapsed = 0
            else:
                elapsed = 0
            ticks = elapsed // farm_catalog.HUNGER_INTERVAL_SECONDS if farm_catalog.HUNGER_INTERVAL_SECONDS else 0
            if ticks > 0:
                old_hunger = hunger
                hunger = min(farm_catalog.HUNGER_MAX, hunger + ticks)
                # 空腹限界を超えて放置した分はポイント減少（赤字要素）
                if old_hunger >= farm_catalog.HUNGER_MAX and hunger >= farm_catalog.HUNGER_MAX:
                    penalty = ticks * farm_catalog.HUNGER_PENALTY_POINTS_PER_TICK
                    conn.execute("UPDATE accounts SET wallet = MAX(0, wallet - ?) WHERE id = ?", (penalty, account_id))
                elif hunger >= farm_catalog.HUNGER_MAX and old_hunger < farm_catalog.HUNGER_MAX:
                    over_ticks = hunger - farm_catalog.HUNGER_MAX + max(0, ticks - (farm_catalog.HUNGER_MAX - old_hunger))
                    # 簡易: 上限到達後の余剰tick分を軽く減点
                    penalty = max(0, over_ticks) * farm_catalog.HUNGER_PENALTY_POINTS_PER_TICK
                    if penalty:
                        conn.execute("UPDATE accounts SET wallet = MAX(0, wallet - ?) WHERE id = ?", (penalty, account_id))
                new_updated_at = (last_dt + timedelta(seconds=ticks * farm_catalog.HUNGER_INTERVAL_SECONDS)).isoformat(timespec="seconds") if hunger_updated_at else now_dt.isoformat(timespec="seconds")
                conn.execute(
                    "UPDATE farm_state SET hunger = ?, hunger_updated_at = ? WHERE account_id = ?",
                    (hunger, new_updated_at, account_id),
                )
                state = conn.execute("SELECT * FROM farm_state WHERE account_id = ?", (account_id,)).fetchone()
            elif not hunger_updated_at:
                conn.execute(
                    "UPDATE farm_state SET hunger_updated_at = ? WHERE account_id = ?",
                    (now_dt.isoformat(timespec="seconds"), account_id),
                )
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
            tool_rows = {
                row["tool_key"]: row
                for row in conn.execute("SELECT * FROM farm_tools WHERE account_id = ?", (account_id,))
            }
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
            personality_key = row["personality"] if "personality" in row.keys() and row["personality"] else "genki"
            personality = farm_catalog.ANIMAL_PERSONALITIES.get(personality_key, farm_catalog.ANIMAL_PERSONALITIES["genki"])
            nickname = row["nickname"] if "nickname" in row.keys() and row["nickname"] else animal["name"]
            bond = row["bond"] if "bond" in row.keys() and row["bond"] is not None else 0
            last_event = row["last_event"] if "last_event" in row.keys() else None
            fullness = self._animal_fullness(row)
            need = int(animal.get("fullness_need", farm_catalog.ANIMAL_PRODUCE_THRESHOLD))
            animals.append({
                "id": row["id"], "key": row["animal"], "name": animal["name"], "emoji": animal["emoji"],
                "product": animal["product"], "product_emoji": animal["product_emoji"],
                "yield": animal["yield"], "resource": animal["resource"],
                "ready": fullness >= need, "remaining": 0,
                "fullness": fullness, "fullness_need": need,
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

        tools = []
        for key, tool in farm_catalog.TOOLS.items():
            owned = key in tool_rows
            prereq = tool.get("prereq")
            prereq_met = prereq is None or prereq in tool_rows
            tools.append({
                "key": key, "name": tool["name"], "emoji": tool["emoji"],
                "grade": tool["grade"], "prereq": prereq,
                "prereq_name": farm_catalog.TOOLS.get(prereq, {}).get("name") if prereq else None,
                "cost": tool["cost"], "description": tool["description"],
                "unlocks": tool.get("unlocks", []),
                "unlock_label": tool.get("unlock_label", ""),
                "owned": owned,
                "acquired_at": tool_rows[key]["acquired_at"] if owned else None,
                "prereq_met": prereq_met,
            })

        blueprints = []
        for key, blueprint in farm_catalog.TOOL_BLUEPRINTS.items():
            owned = key in tool_rows
            prereq = blueprint.get("prereq")
            prereq_met = prereq is None or prereq in tool_rows
            blueprints.append({
                "key": key, "name": blueprint["name"], "emoji": blueprint["emoji"],
                "grade": blueprint["grade"], "prereq": prereq,
                "prereq_name": farm_catalog.TOOLS.get(prereq, {}).get("name", ""),
                "cost": blueprint["cost"], "description": blueprint["description"],
                "unlock_label": blueprint.get("unlock_label", ""),
                "owned": owned, "prereq_met": prereq_met,
            })

        gathers = []
        for key, spot in farm_catalog.GATHER_SPOTS.items():
            row = gather_rows.get(key)
            ready_at = row["ready_at"] if row else farm_catalog.now_iso()
            remaining = farm_catalog.remaining_seconds(ready_at)
            required_tool = spot.get("required_tool")
            tool_owned = required_tool is None or required_tool in tool_rows
            gathers.append({
                "key": key, "name": spot["name"], "emoji": spot["emoji"],
                "resource": spot["resource"], "resource_name": spot["resource_name"],
                "yield": spot["yield"], "interval": spot["interval"],
                "description": spot["description"],
                "ready": remaining == 0 and tool_owned, "remaining": remaining,
                "required_tool": required_tool,
                "required_tool_name": farm_catalog.TOOLS.get(required_tool, {}).get("name") if required_tool else None,
                "locked": not tool_owned,
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
                "hunger": int(state["hunger"] or 0) if "hunger" in state.keys() else 0,
                "hunger_max": farm_catalog.HUNGER_MAX,
            },
            "inventory": inventory,
            "plots": plots,
            "animals": animals,
            "buildings": buildings,
            "tools": tools,
            "blueprints": blueprints,
            "workshop_built": any(row["building"] == "workshop" for row in building_rows),
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

    def _animal_fullness(self, row) -> int:
        """満腹度を取得（放置による減衰を反映）。ready_atを最終更新時刻として使う。"""
        base = row["fullness"] if "fullness" in row.keys() and row["fullness"] is not None else 0
        updated_at = row["ready_at"] if "ready_at" in row.keys() else None
        if updated_at:
            try:
                updated = datetime.fromisoformat(updated_at)
                hours = max(0.0, (datetime.now() - updated).total_seconds() / 3600)
                decay = int(hours * farm_catalog.ANIMAL_FULLNESS_DECAY_PER_HOUR)
                base = base - decay
            except Exception:
                pass
        return max(0, min(farm_catalog.ANIMAL_FULLNESS_MAX, int(base)))

    def buy_animal(self, account_id: int, animal_key: str) -> Dict[str, Any]:
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            animal = farm_catalog.ANIMALS.get(animal_key)
            if not animal:
                raise ValueError("そのどうぶつは いません")
            self._spend(conn, account_id, animal["cost"])
            now = farm_catalog.now_iso()
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
                "INSERT INTO farm_animals (account_id, animal, ready_at, nickname, personality, bond, last_event, fullness) "
                "VALUES (?, ?, ?, ?, ?, 0, NULL, 0)",
                (account_id, animal_key, now, nickname, personality),
            )
            conn.execute("UPDATE farm_state SET exp = exp + 10 WHERE account_id = ?", (account_id,))
        return self.get_farm(account_id)

    def feed_animal(self, account_id: int, animal_id: int, resource: str, amount: int = 1) -> Dict[str, Any]:
        if amount < 1:
            raise ValueError("あげる数は1以上にしてください")
        meta = farm_catalog.RESOURCE_META.get(resource)
        if not meta or meta.get("category") != "food" or int(meta.get("feed_value", 0)) <= 0:
            raise ValueError("その食べ物は どうぶつに あげられません")
        # 畑の収穫物・飼料を中心に許可
        if resource not in {"vegetable", "fruit", "carrot", "feed"}:
            raise ValueError("畑の収穫物や飼料を あげてください")
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            self._ensure_farm_state(conn, account_id)
            row = conn.execute(
                "SELECT * FROM farm_animals WHERE id = ? AND account_id = ?",
                (animal_id, account_id),
            ).fetchone()
            if not row or row["animal"] not in farm_catalog.ANIMALS:
                raise ValueError("どうぶつが 見つかりません")
            inv = self._inventory(conn, account_id)
            if inv.get(resource, 0) < amount:
                raise ValueError(f"{meta['name']} が 足りません")
            self._add_resource(conn, account_id, resource, -amount)

            animal_def = farm_catalog.ANIMALS[row["animal"]]
            fullness = self._animal_fullness(row)
            gain_per = int(meta.get("feed_value", 1)) * 12
            # 好物ボーナス
            if resource in animal_def.get("favorite_food", []):
                gain_per += 6
            fullness = min(farm_catalog.ANIMAL_FULLNESS_MAX, fullness + gain_per * amount)
            bond = row["bond"] if "bond" in row.keys() and row["bond"] is not None else 0
            bond = bond + max(1, amount // 2)
            nickname = row["nickname"] if "nickname" in row.keys() and row["nickname"] else animal_def["name"]
            msg = f"{nickname} に {meta['name']} を あげた！ 満腹度 {fullness}%"
            conn.execute(
                "UPDATE farm_animals SET fullness = ?, bond = ?, last_event = ?, ready_at = ? WHERE id = ?",
                (fullness, bond, msg, farm_catalog.now_iso(), animal_id),
            )
            conn.execute("UPDATE farm_state SET exp = exp + ? WHERE account_id = ?", (amount, account_id))
        data = self.get_farm(account_id)
        data["event"] = {"message": msg}
        return data

    def collect_animal(self, account_id: int, animal_id: int) -> Dict[str, Any]:
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM farm_animals WHERE id = ? AND account_id = ?",
                (animal_id, account_id),
            ).fetchone()
            if not row or row["animal"] not in farm_catalog.ANIMALS:
                raise ValueError("どうぶつが 見つかりません")
            animal_def = farm_catalog.ANIMALS[row["animal"]]
            fullness = self._animal_fullness(row)
            need = int(animal_def.get("fullness_need", farm_catalog.ANIMAL_PRODUCE_THRESHOLD))
            if fullness < need:
                raise ValueError(f"満腹度が足りません（{fullness}% / 必要 {need}%）。畑の収穫物をあげてください。")
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
            new_fullness = max(0, fullness - need)
            conn.execute(
                "UPDATE farm_animals SET fullness = ?, bond = ?, last_event = ?, ready_at = ? WHERE id = ?",
                (new_fullness, new_bond, event["message"], farm_catalog.now_iso(), animal_id),
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
            required_tool = spot.get("required_tool")
            if required_tool:
                has = conn.execute(
                    "SELECT 1 FROM farm_tools WHERE account_id = ? AND tool_key = ?",
                    (account_id, required_tool),
                ).fetchone()
                if not has:
                    tool_name = farm_catalog.TOOLS.get(required_tool, {}).get("name", required_tool)
                    raise ValueError(f"{tool_name} が必要です")
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
            self._spend_cost(conn, account_id, building["cost"])
            conn.execute(
                "INSERT INTO farm_buildings (account_id, building, count) VALUES (?, ?, 1) "
                "ON CONFLICT(account_id, building) DO UPDATE SET count = count + 1",
                (account_id, building_key),
            )
            conn.execute("UPDATE farm_state SET exp = exp + 20 WHERE account_id = ?", (account_id,))
        return self.get_farm(account_id)

    def buy_tool(self, account_id: int, tool_key: str) -> Dict[str, Any]:
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            self._ensure_farm_state(conn, account_id)
            tool = farm_catalog.TOOLS.get(tool_key)
            if not tool:
                raise ValueError("その道具は ありません")
            owned = conn.execute(
                "SELECT 1 FROM farm_tools WHERE account_id = ? AND tool_key = ?",
                (account_id, tool_key),
            ).fetchone()
            if owned:
                raise ValueError("この道具は もう持っています")
            prereq = tool.get("prereq")
            if prereq:
                has_prereq = conn.execute(
                    "SELECT 1 FROM farm_tools WHERE account_id = ? AND tool_key = ?",
                    (account_id, prereq),
                ).fetchone()
                if not has_prereq:
                    prereq_name = farm_catalog.TOOLS.get(prereq, {}).get("name", prereq)
                    raise ValueError(f"先に {prereq_name} が必要です")
            self._spend_cost(conn, account_id, tool["cost"])
            conn.execute(
                "INSERT INTO farm_tools (account_id, tool_key, acquired_at) VALUES (?, ?, ?)",
                (account_id, tool_key, farm_catalog.now_iso()),
            )
            conn.execute("UPDATE farm_state SET exp = exp + 15 WHERE account_id = ?", (account_id,))
        data = self.get_farm(account_id)
        data["event"] = {"message": f"{tool['emoji']} {tool['name']} を 手に入れた！ {tool.get('unlock_label','')}"}
        return data

    def develop_tool(self, account_id: int, tool_key: str) -> Dict[str, Any]:
        """道具工房で設計図の道具を開発する。"""
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            self._ensure_farm_state(conn, account_id)
            blueprint = farm_catalog.TOOL_BLUEPRINTS.get(tool_key)
            if not blueprint:
                raise ValueError("その設計図は ありません")
            has_workshop = conn.execute(
                "SELECT 1 FROM farm_buildings WHERE account_id = ? AND building = 'workshop'",
                (account_id,),
            ).fetchone()
            if not has_workshop:
                raise ValueError("道具工房を 建ててから 開発してください")
            owned = conn.execute(
                "SELECT 1 FROM farm_tools WHERE account_id = ? AND tool_key = ?",
                (account_id, tool_key),
            ).fetchone()
            if owned:
                raise ValueError("この道具は もう持っています")
            prereq = blueprint.get("prereq")
            if prereq:
                has_prereq = conn.execute(
                    "SELECT 1 FROM farm_tools WHERE account_id = ? AND tool_key = ?",
                    (account_id, prereq),
                ).fetchone()
                if not has_prereq:
                    prereq_name = farm_catalog.TOOLS.get(prereq, {}).get("name", prereq)
                    raise ValueError(f"先に {prereq_name} が必要です")
            self._spend_cost(conn, account_id, blueprint["cost"])
            conn.execute(
                "INSERT INTO farm_tools (account_id, tool_key, acquired_at) VALUES (?, ?, ?)",
                (account_id, tool_key, farm_catalog.now_iso()),
            )
            conn.execute("UPDATE farm_state SET exp = exp + 30 WHERE account_id = ?", (account_id,))
        data = self.get_farm(account_id)
        data["event"] = {
            "message": f"🔧 {blueprint['name']} を 工房で 開発した！ {blueprint.get('unlock_label', '')}"
        }
        return data

    def use_tool_action(self, account_id: int, action: str, plot: Optional[int] = None) -> Dict[str, Any]:
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            self._ensure_farm_state(conn, account_id)
            # action -> required tool
            required = None
            for key, tool in farm_catalog.TOOLS.items():
                if action in tool.get("unlocks", []):
                    required = key
                    break
            if not required:
                raise ValueError("その動作は できません")
            has = conn.execute(
                "SELECT 1 FROM farm_tools WHERE account_id = ? AND tool_key = ?",
                (account_id, required),
            ).fetchone()
            if not has:
                tool_name = farm_catalog.TOOLS[required]["name"]
                raise ValueError(f"{tool_name} が必要です")

            message = ""
            if action == "water_crop":
                if plot is None:
                    raise ValueError("水をやる畑を選んでください")
                state = conn.execute("SELECT unlocked_plots FROM farm_state WHERE account_id = ?", (account_id,)).fetchone()
                if plot < 0 or plot >= state["unlocked_plots"]:
                    raise ValueError("この畑は まだ ひらいていません")
                row = conn.execute(
                    "SELECT crop, planted_at FROM farm_plots WHERE account_id = ? AND plot_index = ?",
                    (account_id, plot),
                ).fetchone()
                if not row or row["crop"] not in farm_catalog.CROPS:
                    raise ValueError("この畑には 作物がありません")
                crop = farm_catalog.CROPS[row["crop"]]
                info = farm_catalog.growth_info(row["planted_at"], crop["grow"])
                if info["ready"]:
                    raise ValueError("この作物は もう収穫できます")
                # 成長を30秒早める（planted_atを過去にずらす）
                try:
                    planted = datetime.fromisoformat(row["planted_at"])
                except Exception:
                    planted = datetime.now()
                new_planted = planted - timedelta(seconds=30)
                conn.execute(
                    "UPDATE farm_plots SET planted_at = ? WHERE account_id = ? AND plot_index = ?",
                    (new_planted.isoformat(timespec="seconds"), account_id, plot),
                )
                conn.execute("UPDATE farm_state SET exp = exp + 2 WHERE account_id = ?", (account_id,))
                message = f"{crop['emoji']} {crop['name']} に水をやった！成長が少し早まりました。"
            elif action == "chop_bonus":
                self._add_resource(conn, account_id, "wood", 4)
                conn.execute("UPDATE farm_state SET exp = exp + 3 WHERE account_id = ?", (account_id,))
                message = "オノで木を切って、木材+4 を手に入れた！"
            elif action == "craft_bundle":
                inv = self._inventory(conn, account_id)
                if inv.get("wood", 0) < 3 or inv.get("stone", 0) < 2:
                    raise ValueError("資材加工には 木材3 と 石2 が必要です")
                self._add_resource(conn, account_id, "wood", -3)
                self._add_resource(conn, account_id, "stone", -2)
                self._add_resource(conn, account_id, "iron", 1)
                conn.execute("UPDATE farm_state SET exp = exp + 5 WHERE account_id = ?", (account_id,))
                message = "資材を加工して 鉄+1 を作った！（木材-3, 石-2）"
            else:
                raise ValueError("その動作は まだ使えません")
        data = self.get_farm(account_id)
        data["event"] = {"message": message}
        return data

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

    def convert_to_feed(self, account_id: int, resource: str, amount: int = 1) -> Dict[str, Any]:
        if amount < 1:
            raise ValueError("変換する数は1以上にしてください")
        meta = farm_catalog.RESOURCE_META.get(resource)
        if not meta or meta.get("category") != "food" or resource == "feed":
            raise ValueError("その食材は飼料にできません")
        feed_value = int(meta.get("feed_value", 0))
        if feed_value <= 0:
            raise ValueError("その食材は飼料にできません")
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            self._ensure_farm_state(conn, account_id)
            inventory = self._inventory(conn, account_id)
            if inventory.get(resource, 0) < amount:
                raise ValueError(f"{meta['name']} が足りません")
            self._add_resource(conn, account_id, resource, -amount)
            self._add_resource(conn, account_id, "feed", feed_value * amount)
            conn.execute("UPDATE farm_state SET exp = exp + ? WHERE account_id = ?", (amount, account_id))
        data = self.get_farm(account_id)
        data["event"] = {"message": f"{meta['name']} {amount}個を 飼料 {feed_value * amount}個に変えました！"}
        return data

    def eat(self, account_id: int, resource: str, amount: int = 1) -> Dict[str, Any]:
        if amount < 1:
            raise ValueError("食べる数は1以上にしてください")
        meta = farm_catalog.RESOURCE_META.get(resource)
        eat_value = int(meta.get("eat_value", 0)) if meta else 0
        if not meta or meta.get("category") != "food" or eat_value <= 0:
            raise ValueError("その食べ物は 食べられません")
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            self._ensure_farm_state(conn, account_id)
            inventory = self._inventory(conn, account_id)
            if inventory.get(resource, 0) < amount:
                raise ValueError(f"{meta['name']} が足りません")
            state = conn.execute("SELECT hunger FROM farm_state WHERE account_id = ?", (account_id,)).fetchone()
            hunger = int(state["hunger"] or 0) if state and "hunger" in state.keys() else 0
            self._add_resource(conn, account_id, resource, -amount)
            new_hunger = max(0, hunger - eat_value * amount)
            conn.execute(
                "UPDATE farm_state SET hunger = ?, hunger_updated_at = ? WHERE account_id = ?",
                (new_hunger, farm_catalog.now_iso(), account_id),
            )
        data = self.get_farm(account_id)
        data["event"] = {"message": f"{meta['emoji']} {meta['name']}を食べて、空腹度が {new_hunger}% になりました！"}
        return data

    def clear(self, account_id: Optional[int] = None) -> None:
        with self.lock, self._connect() as conn:
            if account_id is None:
                conn.execute("DELETE FROM answers")
                conn.execute("DELETE FROM point_events")
                conn.execute("DELETE FROM mission_claims")
                conn.execute("DELETE FROM farm_workers")
                conn.execute("DELETE FROM farm_tools")
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
                conn.execute("DELETE FROM farm_tools WHERE account_id = ?", (account_id,))
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

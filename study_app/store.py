"""学習記録・アカウント・ポイントのローカル保存（SQLite）。

外部への送信は行わない。PIN は salt 付き PBKDF2 でハッシュ保存する。
"""
from __future__ import annotations

import hashlib
import hmac
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
                    ready_at TEXT NOT NULL
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

            # 既存DBからの移行
            columns = [row[1] for row in conn.execute("PRAGMA table_info(answers)")]
            if "account_id" not in columns:
                conn.execute("ALTER TABLE answers ADD COLUMN account_id INTEGER")
            account_columns = [row[1] for row in conn.execute("PRAGMA table_info(accounts)")]
            if "wallet" not in account_columns:
                conn.execute("ALTER TABLE accounts ADD COLUMN wallet INTEGER NOT NULL DEFAULT 0")
                conn.execute("UPDATE accounts SET wallet = total_points")
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
            animals.append({
                "id": row["id"], "key": row["animal"], "name": animal["name"], "emoji": animal["emoji"],
                "product": animal["product"], "product_emoji": animal["product_emoji"],
                "yield": animal["yield"], "resource": animal["resource"],
                "ready": remaining == 0, "remaining": remaining,
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
            conn.execute(
                "INSERT INTO farm_animals (account_id, animal, ready_at) VALUES (?, ?, ?)",
                (account_id, animal_key, ready_at),
            )
            conn.execute("UPDATE farm_state SET exp = exp + 10 WHERE account_id = ?", (account_id,))
        return self.get_farm(account_id)

    def collect_animal(self, account_id: int, animal_id: int) -> Dict[str, Any]:
        with self.lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT animal, ready_at FROM farm_animals WHERE id = ? AND account_id = ?",
                (animal_id, account_id),
            ).fetchone()
            if not row or row["animal"] not in farm_catalog.ANIMALS:
                raise ValueError("どうぶつが 見つかりません")
            if farm_catalog.remaining_seconds(row["ready_at"]) > 0:
                raise ValueError("まだ とれるものが ありません")
            animal = farm_catalog.ANIMALS[row["animal"]]
            self._add_resource(conn, account_id, animal["resource"], animal["yield"])
            conn.execute("UPDATE farm_state SET exp = exp + 8 WHERE account_id = ?", (account_id,))
            next_at = (datetime.now() + timedelta(seconds=animal["interval"])).isoformat(timespec="seconds")
            conn.execute("UPDATE farm_animals SET ready_at = ? WHERE id = ?", (next_at, animal_id))
        return self.get_farm(account_id)

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

    def clear(self, account_id: Optional[int] = None) -> None:
        with self.lock, self._connect() as conn:
            if account_id is None:
                conn.execute("DELETE FROM answers")
                conn.execute("DELETE FROM point_events")
                conn.execute("DELETE FROM farm_plots")
                conn.execute("DELETE FROM farm_animals")
                conn.execute("DELETE FROM farm_buildings")
                conn.execute("DELETE FROM farm_inventory")
                conn.execute("DELETE FROM farm_gathers")
                conn.execute("DELETE FROM farm_state")
            else:
                conn.execute("DELETE FROM answers WHERE account_id = ?", (account_id,))
                conn.execute("DELETE FROM point_events WHERE account_id = ?", (account_id,))
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

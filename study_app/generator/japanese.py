"""国語の問題自動生成（小学1〜6年）。

漢字データ: 学年別漢字配当表1026字（スクールコンパス公開データ）
文章・ことばの問題: 本アプリ用にオリジナルで作成（著作権処理済み）
"""
from __future__ import annotations

import random
from typing import Callable, List

from ..config import kanji_by_grade
from .base import Question, pick_choices

Generator = Callable[[random.Random, int, str, str], Question]

HIRAGANA = list("あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん")
KATAKANA = list("アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン")
VOICED = {"か": "が", "き": "ぎ", "く": "ぐ", "け": "げ", "こ": "ご",
          "さ": "ざ", "し": "じ", "す": "ず", "せ": "ぜ", "そ": "ぞ",
          "た": "だ", "ち": "ぢ", "つ": "づ", "て": "で", "と": "ど",
          "は": "ば", "ひ": "び", "ふ": "ぶ", "へ": "べ", "ほ": "ぼ"}

VOCAB = [
    {"grade": 1, "word": "たのしい", "meaning": "心がよろこんでいるようす"},
    {"grade": 1, "word": "かなしい", "meaning": "心が悲しんでいるようす"},
    {"grade": 1, "word": "おおきい", "meaning": "大きさがたくさんあるようす"},
    {"grade": 1, "word": "ちいさい", "meaning": "大きさが少ないようす"},
    {"grade": 2, "word": "元気", "meaning": "体調がよく、活発なようす"},
    {"grade": 2, "word": "静か", "meaning": "音が少なく、おだやかなようす"},
    {"grade": 2, "word": "にぎやか", "meaning": "人が多く、声や音が多いようす"},
    {"grade": 2, "word": "一生けんめい", "meaning": "全力で何かをするようす"},
    {"grade": 3, "word": "大切", "meaning": "とても大事にするようす"},
    {"grade": 3, "word": "丈夫", "meaning": "強くて壊れにくいようす"},
    {"grade": 3, "word": "ぎょうざ", "meaning": "豚肉や野菜を皮で包んだ食べ物"},
    {"grade": 3, "word": "休日", "meaning": "仕事や学校が休みの日"},
    {"grade": 4, "word": "観察", "meaning": "よく見て調べること"},
    {"grade": 4, "word": "実験", "meaning": "確かめるために試すこと"},
    {"grade": 4, "word": "予報", "meaning": "これから起こることを前もって知らせること"},
    {"grade": 4, "word": "りよう", "meaning": "役に立つように使うこと"},
    {"grade": 5, "word": "工夫", "meaning": "より良くするために知恵をしぼること"},
    {"grade": 5, "word": "時計", "meaning": "時を知るための道具"},
    {"grade": 5, "word": "伝統", "meaning": "昔から代々伝わっているもの"},
    {"grade": 5, "word": "必要", "meaning": "どうしても要ること"},
    {"grade": 6, "word": "責任", "meaning": "自分がやるべきことを果たすこと"},
    {"grade": 6, "word": "協力", "meaning": "みんなで力を合わせること"},
    {"grade": 6, "word": "改善", "meaning": "悪いところを良くすること"},
    {"grade": 6, "word": "感謝", "meaning": "ありがたいと思う気持ち"},
]

GRAMMAR = [
    {"grade": 1, "prompt": "わたし __ 小学生です。", "choices": ["は", "を", "に", "で"],
     "answer": "は", "explanation": "「わたしは」と、話の主題を表すときは『は』を使います。"},
    {"grade": 1, "prompt": "ねこ __ えさを たべました。", "choices": ["が", "を", "に", "の"],
     "answer": "が", "explanation": "動作をする人・ものを表すときは『が』を使います。"},
    {"grade": 1, "prompt": "本 __ 読みます。", "choices": ["を", "は", "と", "へ"],
     "answer": "を", "explanation": "動作の対象を表すときは『を』を使います。"},
    {"grade": 2, "prompt": "学校 __ 行きます。", "choices": ["へ", "を", "で", "の"],
     "answer": "へ", "explanation": "向かう先を表すときは『へ』や『に』を使います。"},
    {"grade": 2, "prompt": "昨日、公園 __ 遊びました。", "choices": ["で", "に", "を", "が"],
     "answer": "で", "explanation": "動作の場所を表すときは『で』を使います。"},
    {"grade": 3, "prompt": "この 花は とても __ です。", "choices": ["きれい", "きれいに", "きれいな", "きれいく"],
     "answer": "きれい", "explanation": "「〜は きれいです」のように、形容詞の原形を使います。"},
    {"grade": 3, "prompt": "およぎ __ 上手です。", "choices": ["が", "を", "に", "で"],
     "answer": "が", "explanation": "上手・下手などは『〜が上手』と表します。"},
    {"grade": 4, "prompt": "雨が 降りました。__、試合は 続きました。", "choices": ["しかし", "それで", "したがって", "また"],
     "answer": "しかし", "explanation": "前に述べたことと逆のことが続くので『しかし』が合います。"},
    {"grade": 4, "prompt": "猛烈に 走った __、間に合いました。", "choices": ["ので", "のに", "ため", "から"],
     "answer": "ので", "explanation": "理由から結果が続くので『〜ので』が自然です。"},
    {"grade": 5, "prompt": "先生、この 問題を 説明して __ か。", "choices": ["くださいません", "ください", "なさい", "たまえ"],
     "answer": "くださいません", "explanation": "丁寧にお願いする表現は『〜てくださいませんか』です。"},
    {"grade": 5, "prompt": "お母さんは 台所に __ ます。", "choices": ["い", "お", "あり", "し"],
     "answer": "い", "explanation": "人が存在する場所は『います』、ものは『あります』を使います。"},
    {"grade": 6, "prompt": "彼は 約束を 守るべきだ。__、友だちは 信頼する。", "choices": ["だから", "けれど", "それとも", "まず"],
     "answer": "だから", "explanation": "理由から結論を導く接続には『だから』が合います。"},
]

PROVERBS = [
    {"word": "七転び八起き", "meaning": "何度失敗しても、また立ち上がること"},
    {"word": "初心忘るべからず", "meaning": "初めた頃の気持ちを忘れないようにすること"},
    {"word": "千里の道も一歩から", "meaning": "遠い道のりも、一歩ずつ進めばたどり着くこと"},
    {"word": "二度あることは三度ある", "meaning": "同じことが続けて起こることが多いということ"},
    {"word": "急がば回れ", "meaning": "急ぐときほど、安全な方法を選ぶほうがよいこと"},
    {"word": "灯台下暗し", "meaning": "身近なことほど見落としやすいこと"},
]

PASSAGES = [
    {"grade_min": 1, "grade_max": 2, "title": "こうえんの いちにち",
     "text": "日よう日、わたしは 家族と こうえんへ 行きました。花が たくさん さいていて、ちょうちょが とんで いました。弟は ボールを けって 遊びました。わたしは ベンチに すわって、おべんとうを 食べました。とても たのしい 一日でした。",
     "questions": [
         {"prompt": "だれと こうえんへ 行きましたか。", "choices": ["家族", "先生", "友だち", "ひとり"], "answer": "家族",
          "explanation": "「家族と こうえんへ 行きました」と 書いて あります。"},
         {"prompt": "弟は 何を して 遊びましたか。", "choices": ["ボールを けた", "絵を かいた", "本を 読んだ", "花を 摘んだ"],
          "answer": "ボールを けた", "explanation": "「弟は ボールを けって 遊びました」と あります。"},
     ]},
    {"grade_min": 1, "grade_max": 2, "title": "ねこと おにぎり",
     "text": "給食の 時間に、わたしは おにぎりを 食べました。すると、窓の そばに 小さな ねこが 来ました。ねこは おにぎりを 見て、にゃあと 鳴きました。わたしは 少し 分けて やりました。ねこは うれしそうに 食べて、どこかへ 行きました。",
     "questions": [
         {"prompt": "ねこは どこに 来ましたか。", "choices": ["窓の そば", "机の 中", "こうえん", "ベッドの 下"], "answer": "窓の そば",
          "explanation": "「窓の そばに 小さな ねこが 来ました」と あります。"},
         {"prompt": "わたしは ねこに 何を やりましたか。", "choices": ["おにぎり", "牛乳", "りんご", "おかし"], "answer": "おにぎり",
          "explanation": "「少し 分けて やりました」のは おにぎりです。"},
     ]},
    {"grade_min": 3, "grade_max": 4, "title": "図書館の いっぽう",
     "text": "放課後、わたしは 図書館へ 行きました。しんぶん記事の中に、町の 川に ついての 記事が ありました。以前は 川で 魚が とれたそうですが、今は ごみが 多く、魚は 少なく なりました。町の 人たちは 川を きれいに する 活動を 始めました。わたしも 参加したいと 思いました。",
     "questions": [
         {"prompt": "川に ついて 正しいものは どれですか。", "choices": ["以前は 魚が とれた", "最初から 魚はいなかった", "ごみは 一度も なかった", "活動は 終わった"],
          "answer": "以前は 魚が とれた", "explanation": "「以前は 川で 魚が とれたそうです」と あります。"},
         {"prompt": "「参加したい」の 意味として 近いものは どれですか。", "choices": ["仲間に入りたい", "見に行きたくない", "帰りたい", "忘れたい"],
          "answer": "仲間に入りたい", "explanation": "参加とは、活動の 仲間に入ることです。"},
     ]},
    {"grade_min": 3, "grade_max": 4, "title": "みどりの じゅんび",
     "text": "学校の うら庭で、みどりの 世話を して います。朝、水を やると、土が しめって いました。先週 まいた 種から、小さな 芽が 出て いました。先生は「毎日 少しずつ 世話を 続けることが 大切です」と 言いました。わたしは 日記に 芽の ようすを 書き留めました。",
     "questions": [
         {"prompt": "先生は 何が 大切だと 言いましたか。", "choices": ["毎日 少しずつ 続けること", "一度に たくさん 水を やること", "種を 買い替えること", "日記を 書かないこと"],
          "answer": "毎日 少しずつ 続けること", "explanation": "先生の 言葉に そのまま 書いて あります。"},
         {"prompt": "「書き留めました」の 意味は どれですか。", "choices": ["忘れないように 書いた", "すぐ 消した", "友だちに あげた", "大きな声で 読んだ"],
          "answer": "忘れないように 書いた", "explanation": "書き留めるとは、後で 見られるように 書いて 残すことです。"},
     ]},
    {"grade_min": 5, "grade_max": 6, "title": "古い 時計",
     "text": "親戚の おじいさんの 家に、古い 柱時計が ありました。針は ゆっくり 進み、時々 大きな 音で 時を 知らせました。おじいさんは「この 時計は 祖父から もらった 大切な ものだ」と 話しました。壊れて いても 捨てないのは、時を 測る 道具としてだけでなく、家族の 思い出が こもって いるからです。",
     "questions": [
         {"prompt": "おじいさんが 時計を 大切に する 理由は 何ですか。", "choices": ["家族の 思い出が あるから", "新しいから", "高く 売れるから", "音が 小さいから"],
          "answer": "家族の 思い出が あるから", "explanation": "最後の 文に 理由が 書いて あります。"},
         {"prompt": "「こもって いる」の 意味として 近いものは どれですか。", "choices": ["含まれて いる", "消えて いる", "増えて いる", "離れて いる"],
          "answer": "含まれて いる", "explanation": "思い出が こもると、その物に 思い出が 込められて いるという 意味です。"},
     ]},
    {"grade_min": 5, "grade_max": 6, "title": "雨の しくみ",
     "text": "川や 海の 水は 太陽に 温められて 水蒸気に なります。水蒸気は 空高く 上がり、冷たい 空気に ふれると 小さな 水滴に なって 雲を作ります。水滴が 大きく なり、空気に 支えきれなく なると、雨として 地面に 落ちて きます。雨は 川となって 海へ 戻り、また 同じ 道を めぐります。",
     "questions": [
         {"prompt": "雲は 何から できて いますか。", "choices": ["小さな 水滴", "砂", "風", "太陽の 光"], "answer": "小さな 水滴",
          "explanation": "水蒸気が 冷やされて 水滴に なり、雲が できると 説明して あります。"},
         {"prompt": "この 文章で 説明して いる ものは 何ですか。", "choices": ["雨が 降る しくみ", "時計の しくみ", "植物の 育ち方", "電車の 走り方"],
          "answer": "雨が 降る しくみ", "explanation": "水蒸気から 雨になる までの 流れを 説明して います。"},
     ]},
    {"grade_min": 1, "grade_max": 2, "title": "おかいもの",
     "text": "お母さんと スーパーへ 行きました。りんごを 3 個と、牛乳を 1 本 買いました。お金を 払うと、お店の 人が 「ありがとう」 と 言いました。わたしも 「ありがとう」 と 言いました。",
     "questions": [
         {"prompt": "何を 買いましたか。", "choices": ["りんごと 牛乳", "パンと たまご", "みかんと 水", "おにぎりと おちゃ"], "answer": "りんごと 牛乳",
          "explanation": "「りんごを 3 個と、牛乳を 1 本 買いました」と あります。"},
         {"prompt": "わたしは だれに 「ありがとう」 と 言いましたか。", "choices": ["お店の人", "お母さん", "ねこ", "先生"], "answer": "お店の人",
          "explanation": "お店の 人が 言った 「ありがとう」 に 続いて、わたしも 言いました。"},
     ]},
    {"grade_min": 1, "grade_max": 2, "title": "あめの 日",
     "text": "朝、窓を 見ると 雨が 降って いました。わたしは かさを 持って 学校へ 行きました。帰りには 雨が やんでいて、空に 虹が 出て いました。",
     "questions": [
         {"prompt": "学校へ 行くとき、何を 持って 行きましたか。", "choices": ["かさ", "ぼうし", "てんとう", "ボール"], "answer": "かさ",
          "explanation": "「かさを 持って 学校へ 行きました」と あります。"},
         {"prompt": "帰りに 空に 出て いたのは 何ですか。", "choices": ["虹", "月", "星", "雲"], "answer": "虹",
          "explanation": "「空に 虹が 出て いました」と あります。"},
     ]},
    {"grade_min": 3, "grade_max": 4, "title": "しゃしんの なか",
     "text": "机の 上に 古い 写真が ありました。写真には、若い 祖父と、子どもの ころの 父が 並んで いました。二人は 同じ 木の 下で 笑って います。祖父は 「むかしは この 木の 下で よく 遊んだ」 と 話しました。",
     "questions": [
         {"prompt": "写真に 写って いるのは だれですか。", "choices": ["若い 祖父と 子どもの 父", "わたしと 母", "先生と 友だち", "祖父と 祖母"], "answer": "若い 祖父と 子どもの 父",
          "explanation": "写真の 人物について 最初の ほうで 説明して います。"},
         {"prompt": "祖父は どこで 遊んだと 話しましたか。", "choices": ["この 木の 下", "学校の 庭", "川の そば", "駅の 前"], "answer": "この 木の 下",
          "explanation": "祖父の 話に 「この 木の 下で」 と あります。"},
     ]},
    {"grade_min": 3, "grade_max": 4, "title": "みんなの 当番",
     "text": "金曜日は 教室の 掃除の 日です。わたしたちは 机を 拭き、床を 掃き、窓を 磨きました。最後に ごみを 出して、窓を 閉めました。先生は 「みんなで きれいに できましたね」 と 言いました。",
     "questions": [
         {"prompt": "金曜日は 何の 日ですか。", "choices": ["掃除の 日", "遠足の 日", "試験の 日", "運動会の 日"], "answer": "掃除の 日",
          "explanation": "最初の 文に 「金曜日は 教室の 掃除の 日です」 と あります。"},
         {"prompt": "最後に 何を しましたか。", "choices": ["ごみを 出して 窓を 閉めた", "机を 拭いた", "床を 掃いた", "窓を 磨いた"], "answer": "ごみを 出して 窓を 閉めた",
          "explanation": "「最後に ごみを 出して、窓を 閉めました」と あります。"},
     ]},
    {"grade_min": 5, "grade_max": 6, "title": "駅の エスカレーター",
     "text": "駅で エスカレーターに 乗ると、前の人が 荷物を 落としました。わたしは すぐに 拾って 渡しました。その人は 何度も 礼を 言いました。小さな 親切でも、相手は とても 助かるのだと 思いました。",
     "questions": [
         {"prompt": "駅で 何が 起こりましたか。", "choices": ["前の人が 荷物を 落とした", "エスカレーターが 止まった", "電車が 遅れた", "切符を なくした"], "answer": "前の人が 荷物を 落とした",
          "explanation": "「前の人が 荷物を 落としました」と あります。"},
         {"prompt": "わたしは どんなことを 思いましたか。", "choices": ["小さな 親切でも 役に立つ", "駅は こわい 場所だ", "荷物は 持たない ほうが いい", "礼は いらない"], "answer": "小さな 親切でも 役に立つ",
          "explanation": "最後の 文に わたしの 考えが 書いて あります。"},
     ]},
    {"grade_min": 5, "grade_max": 6, "title": "たんぽぽの たび",
     "text": "たんぽぽの 種は、風に 乗って 遠くへ 飛んで いきます。地面に 落ちた 種は 雨を 吸って 芽を 出します。親の 植物の 近くだけでなく、離れた 場所でも 育つことが できます。これは、種を 遠くへ 運ぶ しくみです。",
     "questions": [
         {"prompt": "たんぽぽの 種は 何に 乗って 飛びますか。", "choices": ["風", "車", "水", "鳥"], "answer": "風",
          "explanation": "「風に 乗って 遠くへ 飛んで いきます」と あります。"},
         {"prompt": "この しくみの よいところは 何ですか。", "choices": ["離れた 場所でも 育つこと", "種が 大きく なること", "花が 早く 咲くこと", "雨が 降らなくて すむこと"], "answer": "離れた 場所でも 育つこと",
          "explanation": "「離れた 場所でも 育つことが できます」と 説明して います。"},
     ]},
]


def _kanji_pool(grade: int) -> List[dict]:
    grouped = kanji_by_grade()
    pool = list(grouped.get(grade, []))
    if not pool:
        pool = [item for key in range(1, 7) for item in grouped[key]]
    return [item for item in pool if item["readings"]]


def gen_kanji_reading(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    pool = _kanji_pool(grade)
    target = rng.choice(pool)
    correct = rng.choice(target["readings"])
    distractors = []
    for item in rng.sample(pool, min(len(pool), 12)):
        if item["char"] == target["char"]:
            continue
        distractors.extend(item["readings"][:1])
    choices = pick_choices(rng, correct, distractors)
    return Question(qid, "国語", grade, "kanji_reading", f"「{target['char']}」の読み方はどれ？",
                    correct, f"「{target['char']}」は「{correct}」と読みます。", choices)


def gen_kanji_strokes(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    pool = [item for item in _kanji_pool(grade) if item["strokes"] > 0]
    target = rng.choice(pool)
    correct = str(target["strokes"])
    wrong = [str(target["strokes"] + delta) for delta in (1, -1, 2, -2) if target["strokes"] + delta > 0]
    return Question(qid, "国語", grade, "kanji_strokes", f"「{target['char']}」は何画ですか？", correct,
                    f"「{target['char']}」は {correct} 画です。", pick_choices(rng, correct, wrong))


def gen_kanji_radical(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    pool = [item for item in _kanji_pool(grade) if item["radical"]]
    target = rng.choice(pool)
    correct = target["radical"]
    wrong = [item["radical"] for item in rng.sample(pool, min(len(pool), 12))
             if item["radical"] != correct]
    return Question(qid, "国語", grade, "kanji_radical", f"「{target['char']}」の部首はどれ？", correct,
                    f"「{target['char']}」の部首は「{correct}」です。", pick_choices(rng, correct, wrong))


def gen_hiragana(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    kind = rng.choice(["next", "kata", "voiced"])
    if kind == "next":
        index = rng.randrange(len(HIRAGANA) - 1)
        char, correct = HIRAGANA[index], HIRAGANA[index + 1]
        prompt = f"五十音で「{char}」のつぎはどれ？"
        note = f"五十音の順番は …{char}{correct}… です。"
        wrong = [HIRAGANA[(index + delta) % len(HIRAGANA)] for delta in (2, 3, 5)]
    elif kind == "kata":
        index = rng.randrange(len(HIRAGANA))
        char, correct = HIRAGANA[index], KATAKANA[index]
        prompt = f"「{char}」をカタカナにするとどれ？"
        note = f"「{char}」のカタカナは「{correct}」です。"
        wrong = [KATAKANA[(index + delta) % len(HIRAGANA)] for delta in (1, 2, 3)]
    else:
        char = rng.choice(list(VOICED))
        correct = VOICED[char]
        prompt = f"「{char}」に濁点をつけるとどれ？"
        note = f"「{char}」に ゛ をつけると「{correct}」です。"
        wrong = [char, rng.choice(list(VOICED)), rng.choice(HIRAGANA)]
    return Question(qid, "国語", grade, "hiragana", prompt, correct, note, pick_choices(rng, correct, wrong))


def gen_vocab(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    pool = [item for item in VOCAB if abs(item["grade"] - grade) <= 1]
    if not pool:
        pool = VOCAB
    target = rng.choice(pool)
    correct = target["meaning"]
    wrong = [item["meaning"] for item in VOCAB if item["word"] != target["word"]]
    return Question(qid, "国語", grade, "vocab", f"「{target['word']}」の意味はどれ？", correct,
                    f"「{target['word']}」とは {correct} という意味です。", pick_choices(rng, correct, wrong))


def gen_grammar(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    pool = [item for item in GRAMMAR if abs(item["grade"] - grade) <= 1]
    if not pool:
        pool = GRAMMAR
    target = rng.choice(pool)
    return Question(qid, "国語", grade, "grammar", target["prompt"], target["answer"],
                    target["explanation"], list(target["choices"]))


def gen_proverb(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    target = rng.choice(PROVERBS)
    wrong = [item["meaning"] for item in PROVERBS if item["word"] != target["word"]]
    return Question(qid, "国語", grade, "proverb", f"「{target['word']}」の意味はどれ？", target["meaning"],
                    f"「{target['word']}」とは {target['meaning']} という意味です。",
                    pick_choices(rng, target["meaning"], wrong))


def gen_reading(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    pool = [p for p in PASSAGES if p["grade_min"] <= grade <= p["grade_max"]]
    if not pool:
        pool = PASSAGES
    passage = rng.choice(pool)
    item = rng.choice(passage["questions"])
    return Question(qid, "国語", grade, "reading", item["prompt"], item["answer"],
                    item["explanation"], list(item["choices"]), passage["text"])


GENERATORS: dict = {
    "kanji_reading": gen_kanji_reading, "kanji_strokes": gen_kanji_strokes,
    "kanji_radical": gen_kanji_radical, "hiragana": gen_hiragana,
    "vocab": gen_vocab, "grammar": gen_grammar, "proverb": gen_proverb, "reading": gen_reading,
}

JAPANESE_TOPICS: dict = {
    1: [("hiragana", "ひらがな・カタカナ"), ("kanji_reading", "漢字の読み"),
        ("vocab", "ことばの意味"), ("grammar", "ことばの使い方"), ("reading", "文章を読む")],
    2: [("kanji_reading", "漢字の読み"), ("kanji_strokes", "漢字の画数"),
        ("hiragana", "ひらがな・カタカナ"), ("vocab", "ことばの意味"),
        ("grammar", "ことばの使い方"), ("reading", "文章を読む")],
    3: [("kanji_reading", "漢字の読み"), ("kanji_strokes", "漢字の画数"),
        ("kanji_radical", "漢字の部首"), ("vocab", "ことばの意味"),
        ("grammar", "ことばの使い方"), ("reading", "文章を読む")],
    4: [("kanji_reading", "漢字の読み"), ("kanji_radical", "漢字の部首"),
        ("vocab", "ことばの意味"), ("grammar", "ことばの使い方"), ("reading", "文章を読む")],
    5: [("kanji_reading", "漢字の読み"), ("kanji_radical", "漢字の部首"),
        ("vocab", "ことばの意味"), ("grammar", "ことばの使い方"),
        ("proverb", "ことわざ"), ("reading", "文章を読む")],
    6: [("kanji_reading", "漢字の読み"), ("kanji_radical", "漢字の部首"),
        ("vocab", "ことばの意味"), ("grammar", "ことばの使い方"),
        ("proverb", "ことわざ"), ("reading", "文章を読む")],
}

(() => {
  const $ = (id) => document.getElementById(id);
  const state = {
    cfg: null,
    accounts: [],
    account: null,
    grade: 1,
    subject: 'math',
    topics: new Set(),
    count: 10,
    difficulty: 'normal',
    adaptive: false,
    quizId: null,
    questions: [],
    index: 0,
    correct: 0,
    earnedTotal: 0,
    locked: false,
    view: 'drill',
    farm: null,
    selectedCrop: 'cabbage',
    farmTimer: null,
    farmSignature: null,
  };

  const sections = { setup: $('setup'), quiz: $('quiz'), result: $('result') };
  const RES_NAMES = { vegetable: '野菜', fruit: 'くだもの', egg: 'たまご', milk: 'ミルク', carrot: 'にんじん', feed: '飼料', wood: '木材', stone: '石', coal: '石炭', iron: '鉄' };
  const resLabel = (key) => RES_NAMES[key] || key;
  const show = (name) => {
    Object.entries(sections).forEach(([key, el]) => el.classList.toggle('hidden', key !== name));
  };

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function makeChip(text, selected, onClick, className = 'chip') {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = className + (selected ? ' selected' : '');
    button.textContent = text;
    button.addEventListener('click', onClick);
    return button;
  }

  function updateBadge(account) {
    if (!account) {
      $('account-badge').textContent = 'アカウントを えらんでね';
      return;
    }
    $('account-badge').textContent =
      `${account.nickname} · Lv.${account.level} ${account.level_title} · 使える ${account.wallet} pt（累計 ${account.total_points}） · 連続${account.streak}`;
  }

  function syncAccount(updated) {
    state.account = updated;
    const index = state.accounts.findIndex((item) => item.id === updated.id);
    if (index >= 0) state.accounts[index] = updated;
    updateBadge(updated);
  }

  function renderAccounts() {
    const select = $('account-select');
    select.innerHTML = '';
    state.accounts.forEach((account) => {
      const option = document.createElement('option');
      option.value = String(account.id);
      option.textContent = `${account.nickname}（Lv.${account.level}・${account.total_points} pt${account.has_pin ? '・PINあり' : ''}）`;
      select.appendChild(option);
    });
    if (state.account) select.value = String(state.account.id);
  }

  async function selectAccount(accountId, options = {}) {
    const account = state.accounts.find((item) => item.id === accountId);
    if (!account) return;
    let pin = null;
    let trusted = Boolean(options.trusted);
    if (!trusted && account.has_pin) {
      pin = prompt(`${account.nickname} の PIN（4けた）を いれてね`);
      if (pin === null) return;
    }
    try {
      const updated = await api(`/api/accounts/${accountId}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pin, trusted }),
      });
      state.accounts = await api('/api/accounts');
      syncAccount(updated);
      renderAccounts();
      localStorage.setItem('study_account_id', String(updated.id));
      await loadProgress();
      await loadAnalysis();
      if (state.view === 'farm') await loadFarm();
    } catch (error) {
      alert(error.message);
    }
  }

  function renderFilters() {
    const grades = $('grades');
    grades.innerHTML = '';
    state.cfg.grades.forEach((g) => {
      grades.appendChild(makeChip(g.label, g.value === state.grade, () => {
        state.grade = g.value;
        state.topics.clear();
        renderFilters();
      }));
    });

    const subjects = $('subjects');
    subjects.innerHTML = '';
    state.cfg.subjects.forEach((s) => {
      subjects.appendChild(makeChip(s.label, s.key === state.subject, () => {
        state.subject = s.key;
        state.topics.clear();
        renderFilters();
      }, 'chip subject-tab'));
    });

    const topics = $('topics');
    topics.innerHTML = '';
    const list = state.cfg.topics[state.subject][String(state.grade)] || [];
    list.forEach((t) => {
      const button = makeChip(t.label, state.topics.has(t.key), () => {
        if (state.topics.has(t.key)) state.topics.delete(t.key);
        else state.topics.add(t.key);
        renderFilters();
      }, 'topic');
      button.classList.toggle('selected', state.topics.has(t.key));
      topics.appendChild(button);
    });

    const diff = $('difficulty');
    if (!diff.options.length) {
      state.cfg.difficulties.forEach((d) => {
        const option = document.createElement('option');
        option.value = d.key;
        option.textContent = d.label;
        diff.appendChild(option);
      });
    }
    diff.value = state.difficulty;
  }

  async function api(path, options) {
    const response = await fetch(path, options);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || '通信に失敗しました');
    }
    return response.json();
  }

  async function startQuiz() {
    if (!state.account) {
      alert('まず アカウントを えらんでね');
      return;
    }
    try {
      const data = await api('/api/quiz', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          grade: state.grade,
          subject: state.subject,
          topics: Array.from(state.topics),
          count: state.count,
          difficulty: state.difficulty,
          adaptive: state.adaptive,
          account_id: state.account.id,
        }),
      });
      state.quizId = data.quiz_id;
      state.questions = data.questions;
      state.index = 0;
      state.correct = 0;
      state.earnedTotal = 0;
      show('quiz');
      renderQuestion();
    } catch (error) {
      alert(error.message);
    }
  }

  function renderQuestion() {
    const question = state.questions[state.index];
    const total = state.questions.length;
    state.locked = false;

    $('progress-label').textContent = `${state.index + 1} / ${total} 問`;
    $('progress-bar').style.width = `${(state.index / total) * 100}%`;

    const passage = $('passage');
    passage.textContent = question.passage || '';
    passage.classList.toggle('hidden', !question.passage);
    $('question').textContent = question.prompt;

    const choices = $('choices');
    const inputArea = $('input-area');
    choices.innerHTML = '';
    inputArea.classList.toggle('hidden', question.choices.length > 0);
    choices.classList.toggle('hidden', question.choices.length === 0);

    question.choices.forEach((choice) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'choice';
      button.textContent = choice;
      button.addEventListener('click', () => submitAnswer(choice, button));
      choices.appendChild(button);
    });

    $('feedback').classList.add('hidden');
    $('next').classList.add('hidden');
    const input = $('answer-input');
    input.value = '';
    input.focus();
  }

  async function submitAnswer(value, button) {
    if (state.locked) return;
    state.locked = true;
    document.querySelectorAll('.choice').forEach((el) => { el.disabled = true; });
    $('submit').disabled = true;

    try {
      const result = await api(`/api/quiz/${state.quizId}/answer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question_id: state.questions[state.index].id, answer: value }),
      });
      if (result.correct) state.correct += 1;
      state.earnedTotal += result.earned;
      syncAccount(result.account);
      if (button) button.classList.add(result.correct ? 'correct' : 'wrong');

      const feedback = $('feedback');
      feedback.className = 'feedback ' + (result.correct ? 'ok' : 'ng');
      feedback.innerHTML = '';
      const headline = document.createElement('div');
      headline.textContent = result.correct ? 'せいかい！ 🎉' : 'おしい！ こたえは 「' + result.correct_answer + '」';
      const note = document.createElement('span');
      note.className = 'note';
      note.textContent = `${result.explanation}　／　+${result.earned} pt（合計 ${result.account.total_points} pt）`;
      feedback.appendChild(headline);
      feedback.appendChild(note);
      if (result.encounters && result.encounters.length) {
        result.encounters.forEach((enc) => {
          const box = document.createElement('div');
          box.className = 'encounter-note';
          box.textContent = `🤝 ${enc.message} 農場で雇えるようになりました！`;
          feedback.appendChild(box);
        });
      }
      feedback.classList.remove('hidden');

      const next = $('next');
      next.textContent = state.index + 1 >= state.questions.length ? '結果を見る ▶' : 'つぎの問題へ ▶';
      next.classList.remove('hidden');
    } catch (error) {
      alert(error.message);
      state.locked = false;
    } finally {
      $('submit').disabled = false;
    }
  }

  async function showResult() {
    try {
      const result = await api(`/api/quiz/${state.quizId}/result`);
      const rate = result.total ? Math.round((result.correct / result.total) * 100) : 0;
      const stars = rate >= 90 ? 3 : rate >= 70 ? 2 : rate >= 50 ? 1 : 0;
      $('stars').textContent = '★'.repeat(stars) + '☆'.repeat(3 - stars);
      $('result-title').textContent = stars === 3 ? 'よくできました！' : stars >= 1 ? 'いいがんばり！' : 'つぎは がんばろう！';
      $('result-detail').textContent = `${result.correct} / ${result.total} 問 せいかい（${rate}%）`;
      $('earned-points').textContent = `このクイズで +${state.earnedTotal} pt げっと！ 合計 ${state.account.total_points} pt`;

      const review = $('review');
      review.innerHTML = '';
      result.items.filter((item) => !item.correct).forEach((item) => {
        const div = document.createElement('div');
        div.className = 'review-item';
        const title = document.createElement('b');
        title.textContent = item.prompt;
        const note = document.createElement('div');
        note.textContent = `こたえ: ${item.correct_answer}／${item.explanation}`;
        div.appendChild(title);
        div.appendChild(note);
        review.appendChild(div);
      });
      show('result');
      await loadProgress();
      await loadAnalysis();
    } catch (error) {
      alert(error.message);
    }
  }

  function renderPointList(element, items, withTime) {
    element.innerHTML = '';
    items.forEach((item) => {
      const div = document.createElement('div');
      div.className = 'point-item';
      const label = document.createElement('span');
      label.textContent = item.reason + (withTime ? `（${item.created_at}）` : '');
      const amount = document.createElement('span');
      amount.className = 'plus';
      amount.textContent = `+${item.amount}`;
      div.appendChild(label);
      div.appendChild(amount);
      element.appendChild(div);
    });
    if (!items.length) element.textContent = 'まだ ありません';
  }

  async function loadProgress() {
    if (!state.account) return;
    try {
      const data = await api(`/api/progress?account_id=${state.account.id}`);
      syncAccount(data.account);

      const stats = $('progress-summary');
      stats.innerHTML = '';
      [
        { label: 'ポイント', value: data.account.total_points },
        { label: 'レベル', value: `Lv.${data.account.level}` },
        { label: '連続せいかい', value: data.account.streak },
        { label: 'といた問題', value: data.summary.total },
        { label: 'せいかい率', value: `${data.summary.accuracy}%` },
      ].forEach((item) => {
        const box = document.createElement('div');
        box.className = 'stat';
        const value = document.createElement('span');
        value.className = 'value';
        value.textContent = item.value;
        const label = document.createElement('span');
        label.className = 'label';
        label.textContent = item.label;
        box.appendChild(value);
        box.appendChild(label);
        stats.appendChild(box);
      });

      renderPointList($('point-breakdown'), data.point_breakdown, false);
      renderPointList($('point-events'), data.recent_events, true);

      const list = $('wrong-list');
      list.innerHTML = '';
      data.summary.recent_wrong.forEach((item) => {
        const div = document.createElement('div');
        div.className = 'wrong-item';
        div.textContent = `${item.prompt} → こたえ: ${item.correct_answer}`;
        const time = document.createElement('span');
        time.textContent = `（${item.created_at}）`;
        div.appendChild(time);
        list.appendChild(div);
      });
    } catch (error) {
      console.error(error);
    }
  }

  async function loadAnalysis() {
    if (!state.account) return;
    try {
      const data = await api(`/api/accounts/${state.account.id}/analysis`);
      syncAccount(data.account);
      renderMissions(data.missions || []);
      renderWeakTopics(data.weak_topics || []);
    } catch (error) {
      console.error(error);
    }
  }

  function renderMissions(missions) {
    const list = $('mission-list');
    list.innerHTML = '';
    if (!missions.length) {
      list.textContent = 'ミッションは ありません';
      return;
    }
    missions.forEach((mission) => {
      const card = el('div', 'mission-card' + (mission.claimed ? ' claimed' : mission.done ? ' done' : ''));
      const head = el('div', 'mission-head');
      head.appendChild(el('div', 'mission-title', mission.title));
      const status = mission.claimed ? '受取済み' : mission.done ? '達成！' : `${mission.progress}/${mission.goal}`;
      head.appendChild(el('div', 'mission-status', status));
      card.appendChild(head);
      card.appendChild(el('div', 'mission-desc', mission.description));
      const resNames = { food: '食料', wood: '木材', stone: '石', coal: '石炭', iron: '鉄' };
      const rewards = [`+${mission.reward_points}pt`].concat(
        Object.entries(mission.reward_resources || {}).map(([k, v]) => `${resNames[k] || k}+${v}`)
      );
      card.appendChild(el('div', 'mission-reward', `ほうしゅう: ${rewards.join(' / ')}`));
      if (!mission.claimed) {
        const btn = el('button', 'small-btn' + (mission.done ? ' sub' : ''));
        btn.type = 'button';
        btn.textContent = mission.done ? '受け取る' : 'まだ';
        btn.disabled = !mission.done;
        btn.addEventListener('click', async () => {
          try {
            const data = await api('/api/missions/claim', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ account_id: state.account.id, mission_key: mission.key }),
            });
            syncAccount(data.account);
            renderMissions(data.missions || []);
            renderWeakTopics(data.weak_topics || []);
            await loadProgress();
            if (state.view === 'farm') await loadFarm();
            alert(`${mission.title} のほうしゅうを 受け取ったよ！`);
          } catch (error) {
            alert(error.message);
          }
        });
        card.appendChild(btn);
      }
      list.appendChild(card);
    });
  }

  function renderWeakTopics(topics) {
    const list = $('weak-topics');
    list.innerHTML = '';
    if (!topics.length) {
      list.textContent = 'まだ 分析データが ありません。問題を とくと にがてが 見えてきます。';
      return;
    }
    topics.forEach((item) => {
      const row = el('div', 'weak-item');
      const label = el('div', 'weak-label', `${item.subject} / ${item.topic}`);
      const meta = el('div', 'weak-meta', `正答率 ${item.accuracy}%（${item.correct}/${item.total}）`);
      row.appendChild(label);
      row.appendChild(meta);
      list.appendChild(row);
    });
  }

  async function createAccount() {
    const nickname = $('new-nickname').value.trim();
    const pin = $('new-pin').value.trim();
    if (!nickname || !/^\d{4}$/.test(pin)) {
      alert('なまえと PIN（4けた）を 入れてね');
      return;
    }
    try {
      const created = await api('/api/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nickname, pin }),
      });
      $('account-form').classList.add('hidden');
      $('new-nickname').value = '';
      $('new-pin').value = '';
      await selectAccount(created.id, { trusted: true });
    } catch (error) {
      alert(error.message);
    }
  }

  async function deleteAccount() {
    if (!state.account) return;
    if (!confirm(`${state.account.nickname} の 記録を 全部 消しますか？`)) return;
    let pin = null;
    let trusted = true;
    if (state.account.has_pin) {
      pin = prompt('PIN（4けた）を いれてね');
      if (pin === null) return;
      trusted = false;
    }
    try {
      await api(`/api/accounts/${state.account.id}/delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pin, trusted }),
      });
      state.accounts = await api('/api/accounts');
      localStorage.removeItem('study_account_id');
      await selectAccount(state.accounts[0].id, { trusted: true });
    } catch (error) {
      alert(error.message);
    }
  }

  // ---------------- 農場GUI ----------------
  const farmGame = (() => {
    const canvas = $('farm-canvas');
    const ctx = canvas.getContext('2d');
    const panel = $('farm-action-panel');
    const player = { x: 480, y: 300, tx: 480, ty: 300, speed: 180, moving: false, facing: 'down' };
    let interactables = [];
    let selected = null;
    let lastTs = 0;
    let raf = 0;
    let nowMs = 0;
    const anim = new Map();

    function toCanvasPos(evt) {
      const rect = canvas.getBoundingClientRect();
      return {
        x: (evt.clientX - rect.left) * (canvas.width / rect.width),
        y: (evt.clientY - rect.top) * (canvas.height / rect.height),
      };
    }

    function dist(a, b) { return Math.hypot(a.x - b.x, a.y - b.y); }
    function itemPos(it) {
      const a = anim.get(it.id);
      if (!a) return { x: it.x, y: it.y };
      if (it.type === 'animal') return { x: it.x + a.ox, y: it.y + a.oy + Math.sin(nowMs / 350 + a.phase) * 2 };
      if (it.type === 'worker') return { x: it.x + a.ox, y: it.y + a.oy };
      if (it.type === 'gather') return { x: it.x, y: it.y + (a.oy || 0) };
      return { x: it.x, y: it.y };
    }

    function hidePanel() { panel.classList.add('hidden'); panel.innerHTML = ''; }

    function showPanel(item) {
      selected = item;
      panel.innerHTML = '';
      panel.appendChild(el('h3', '', item.title));
      panel.appendChild(el('p', '', item.info || ''));
      if (item.detail) panel.appendChild(el('p', '', item.detail));
      const actions = el('div', 'actions');
      (item.actions || []).forEach((a) => {
        const btn = el('button', 'small-btn' + (a.primary ? ' sub' : ''));
        btn.type = 'button';
        btn.textContent = a.label;
        btn.disabled = !!a.disabled;
        btn.addEventListener('click', () => a.run());
        actions.appendChild(btn);
      });
      const close = el('button', 'small-btn');
      close.type = 'button';
      close.textContent = 'とじる';
      close.addEventListener('click', () => { selected = null; hidePanel(); });
      actions.appendChild(close);
      panel.appendChild(actions);
      panel.classList.remove('hidden');
    }

    function buildInteractables(data) {
      const items = [];
      const accountId = state.account.id;
      const plots = data.plots.filter(p => p.unlocked);
      const cols = 6;
      const plotW = 92, plotH = 72, startX = 40, startY = 90;
      plots.forEach((plot, i) => {
        const col = i % cols;
        const row = Math.floor(i / cols);
        const x = startX + col * (plotW + 14) + plotW / 2;
        const y = startY + row * (plotH + 14) + plotH / 2;
        const actions = [];
        if (!plot.crop) {
          actions.push({ label: 'たねを植える', primary: true, run: () => farmPost('/api/farm/plant', { account_id: accountId, plot: plot.index, crop: state.selectedCrop }) });
        } else if (plot.ready) {
          actions.push({ label: '収穫する', primary: true, run: () => farmPost('/api/farm/harvest', { account_id: accountId, plot: plot.index }) });
        }
        items.push({
          id: `plot-${plot.index}`, type: 'plot', x, y, w: plotW, h: plotH, r: 52,
          title: `畑 ${plot.index + 1}`, plot,
          info: !plot.crop ? '空き畑です。たねを植えられます。' : plot.ready ? `${plot.emoji} ${plot.name} が収穫できます！` : `${plot.emoji} ${plot.name} 育成中`,
          detail: !plot.crop ? `選択中のたね: ${state.selectedCrop}` : plot.ready ? `${resLabel(plot.resource)}+${plot.yield || 0}` : `あと ${plot.remaining} 秒`,
          actions,
        });
      });

      (data.gathers || []).forEach((g, i) => {
        const x = 90 + i * 150;
        const y = 430;
        const locked = !!g.locked;
        items.push({
          id: `gather-${g.key}`, type: 'gather', x, y, r: 42, gather: g,
          title: `${g.emoji} ${g.name}`,
          info: locked ? `🔒 ${g.required_tool_name || '道具'} が必要` : g.ready ? `${g.resource_name}を集められます` : `あと ${g.remaining} 秒`,
          detail: `${g.resource_name}+${g.yield}`,
          actions: [{ label: locked ? '道具が必要' : g.ready ? '集める' : '準備中', primary: g.ready, disabled: !g.ready || locked, run: () => farmPost('/api/farm/gather', { account_id: accountId, spot: g.key }) }],
        });
      });

      (data.animals || []).forEach((a, i) => {
        const x = 690 + (i % 3) * 85;
        const y = 120 + Math.floor(i / 3) * 70;
        const feedableKeys = ['vegetable','fruit','carrot','feed'];
        const feedRes = feedableKeys.find(k => ((data.inventory || {})[k] || 0) > 0) || 'vegetable';
        const fullness = Number(a.fullness || 0);
        const need = Number(a.fullness_need || 80);
        items.push({
          id: `animal-${a.id}`, type: 'animal', x, y, r: 34, animal: a,
          title: `${a.emoji} ${a.nickname || a.name}`,
          info: a.ready ? `${a.product_emoji} ${a.product} がとれます` : `満腹度 ${fullness}% / ${need}%`,
          detail: `なかよし度 ${a.bond ?? 0} ・ えさ: ${resLabel(feedRes)}`,
          actions: [
            { label: 'えさをあげる', primary: !a.ready, disabled: false, run: () => farmPost('/api/farm/feed-animal', { account_id: accountId, animal_id: a.id, resource: feedRes, amount: 1 }) },
            { label: a.ready ? '集める' : 'まだ', primary: a.ready, disabled: !a.ready, run: () => farmPost('/api/farm/collect-animal', { account_id: accountId, animal_id: a.id }) },
          ],
        });
      });

      (data.workers || []).forEach((w, i) => {
        const x = 690 + (i % 3) * 85;
        const y = 320 + Math.floor(i / 3) * 75;
        const actions = [];
        if (!w.hired) actions.push({ label: '雇う', primary: true, run: () => farmPost('/api/farm/hire-worker', { account_id: accountId, worker_key: w.key }) });
        else actions.push({ label: w.ready ? '受け取る' : 'はたらき中', primary: w.ready, disabled: !w.ready, run: () => farmPost('/api/farm/collect-worker', { account_id: accountId, worker_key: w.key }) });
        items.push({
          id: `worker-${w.key}`, type: 'worker', x, y, r: 34, worker: w,
          title: `${w.emoji} ${w.name}`,
          info: !w.hired ? `出会った人。雇えます` : w.ready ? '仕事完了！' : `あと ${w.remaining} 秒`,
          detail: w.hired ? '' : '雇用コストは下のカードでも確認できます',
          actions,
        });
      });

      interactables = items;
      items.forEach((it) => {
        if (!anim.has(it.id)) {
          anim.set(it.id, {
            ox: 0, oy: 0, vx: (Math.random() - 0.5) * 20, vy: (Math.random() - 0.5) * 20,
            phase: Math.random() * Math.PI * 2, nextDir: Math.random() * 2,
          });
        }
      });
      if (selected) {
        const fresh = items.find(it => it.id === selected.id);
        if (fresh && dist(player, itemPos(fresh)) < fresh.r + 40) showPanel(fresh);
        else { selected = null; hidePanel(); }
      }
    }

    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      // background
      ctx.fillStyle = '#cfeec4';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#b9dfae';
      ctx.fillRect(0, 380, canvas.width, 160);
      ctx.fillStyle = '#efe0b8';
      ctx.fillRect(20, 70, 660, 290);
      ctx.strokeStyle = '#d2c08f';
      ctx.strokeRect(20, 70, 660, 290);
      ctx.fillStyle = '#f7efd3';
      ctx.fillRect(660, 70, 280, 440);
      ctx.fillStyle = '#5a7b46';
      ctx.font = 'bold 18px sans-serif';
      ctx.fillText('畑エリア', 30, 62);
      ctx.fillText('どうぶつ・働き手', 670, 62);
      ctx.fillText('採集エリア', 30, 402);

      interactables.forEach((it) => {
        const a = anim.get(it.id) || { ox: 0, oy: 0, phase: 0 };
        if (it.type === 'plot') {
          const p = it.plot;
          const pulse = p.ready ? (Math.sin(nowMs / 220 + a.phase) * 0.5 + 0.5) : 0;
          ctx.fillStyle = !p.crop ? '#d8b07a' : p.ready ? `rgb(${155 + pulse * 35}, ${210 + pulse * 20}, ${126 + pulse * 20})` : '#bcdca0';
          ctx.fillRect(it.x - it.w / 2, it.y - it.h / 2, it.w, it.h);
          ctx.strokeStyle = selected && selected.id === it.id ? '#ff8a00' : '#8b6a3e';
          ctx.lineWidth = selected && selected.id === it.id ? 4 : 2;
          ctx.strokeRect(it.x - it.w / 2, it.y - it.h / 2, it.w, it.h);
          if (p.crop) {
            const sway = p.ready ? Math.sin(nowMs / 260 + a.phase) * 3 : Math.sin(nowMs / 700 + a.phase) * 1.5;
            ctx.save();
            ctx.translate(it.x + sway, it.y + 2);
            ctx.font = '24px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillStyle = '#3f3a2f';
            ctx.fillText(p.emoji, 0, 0);
            ctx.restore();
          } else {
            ctx.fillStyle = '#6b5330';
            ctx.font = '24px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('＋', it.x, it.y + 4);
          }
          ctx.fillStyle = '#3f3a2f';
          ctx.font = '12px sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText(p.crop ? (p.ready ? '収穫OK' : `${p.remaining}s`) : '空き', it.x, it.y + 28);
        } else if (it.type === 'gather') {
          const g = it.gather;
          const bob = a.oy || 0;
          ctx.beginPath();
          ctx.fillStyle = g.locked ? '#c8c8c8' : g.ready ? '#8fd0ff' : '#9ec5de';
          ctx.arc(it.x, it.y + bob, 34, 0, Math.PI * 2);
          ctx.fill();
          ctx.strokeStyle = selected && selected.id === it.id ? '#ff8a00' : '#4f88aa';
          ctx.lineWidth = selected && selected.id === it.id ? 4 : 2;
          ctx.stroke();
          if (g.ready && !g.locked) {
            ctx.strokeStyle = 'rgba(255,255,255,.8)';
            ctx.lineWidth = 2;
            ctx.beginPath(); ctx.arc(it.x, it.y + bob, 40 + Math.sin(nowMs / 220 + a.phase) * 2, 0, Math.PI * 2); ctx.stroke();
          }
          ctx.fillStyle = '#203040';
          ctx.font = '26px sans-serif'; ctx.textAlign = 'center'; ctx.fillText(g.locked ? '🔒' : g.emoji, it.x, it.y + 4 + bob);
          ctx.font = '12px sans-serif'; ctx.fillText(g.name, it.x, it.y + 52 + bob);
        } else if (it.type === 'animal' || it.type === 'worker') {
          const obj = it.animal || it.worker;
          const ax = it.x + a.ox;
          const ay = it.y + a.oy + (it.type === 'animal' ? Math.sin(nowMs / 350 + a.phase) * 2 : 0);
          ctx.fillStyle = 'rgba(0,0,0,.1)';
          ctx.beginPath(); ctx.ellipse(ax, ay + 24, 14, 5, 0, 0, Math.PI * 2); ctx.fill();
          ctx.beginPath();
          ctx.fillStyle = it.type === 'worker' ? (obj.hired ? '#fff2b0' : '#ffe0e0') : '#fff8dd';
          ctx.arc(ax, ay, 28, 0, Math.PI * 2);
          ctx.fill();
          ctx.strokeStyle = selected && selected.id === it.id ? '#ff8a00' : '#bba86a';
          ctx.lineWidth = selected && selected.id === it.id ? 4 : 2;
          ctx.stroke();
          ctx.fillStyle = '#333';
          ctx.font = '24px sans-serif'; ctx.textAlign = 'center';
          ctx.fillText(obj.emoji, ax, ay + 6);
          ctx.font = '11px sans-serif';
          const label = it.type === 'worker' ? obj.name : (obj.nickname || obj.name);
          ctx.fillText(label, ax, ay + 44);
          if (it.type === 'animal' && it.animal.ready) {
            ctx.fillStyle = '#ff9f1a';
            ctx.font = '14px sans-serif';
            ctx.fillText('!', ax + 20, ay - 16);
          }
        }
      });

      // target marker
      if (player.moving) {
        ctx.strokeStyle = 'rgba(255,120,0,.8)';
        ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(player.tx, player.ty, 10, 0, Math.PI * 2); ctx.stroke();
      }

      // player
      ctx.save();
      ctx.translate(player.x, player.y);
      ctx.fillStyle = 'rgba(0,0,0,.15)';
      ctx.beginPath(); ctx.ellipse(0, 18, 16, 6, 0, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#4f7cff';
      ctx.fillRect(-12, -4, 24, 22);
      ctx.fillStyle = '#ffd8b0';
      ctx.beginPath(); ctx.arc(0, -14, 12, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#6b3f1d';
      ctx.beginPath(); ctx.arc(0, -18, 12, Math.PI, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#333';
      ctx.fillRect(-4, -16, 2, 2); ctx.fillRect(2, -16, 2, 2);
      ctx.fillStyle = '#2d5b2d';
      ctx.fillRect(-14, 12, 10, 10); ctx.fillRect(4, 12, 10, 10);
      ctx.restore();
      ctx.textAlign = 'left';
    }

    function update(dt) {
      nowMs += dt * 1000;
      const dx = player.tx - player.x;
      const dy = player.ty - player.y;
      const d = Math.hypot(dx, dy);
      if (d > 2) {
        player.moving = true;
        const step = Math.min(d, player.speed * dt);
        player.x += dx / d * step;
        player.y += dy / d * step;
        player.facing = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 'right' : 'left') : (dy > 0 ? 'down' : 'up');
      } else {
        player.moving = false;
      }

      interactables.forEach((it) => {
        const a = anim.get(it.id);
        if (!a) return;
        if (it.type === 'animal') {
          a.nextDir -= dt;
          if (a.nextDir <= 0) {
            a.vx = (Math.random() - 0.5) * 26;
            a.vy = (Math.random() - 0.5) * 18;
            a.nextDir = 1.2 + Math.random() * 2.2;
          }
          a.ox += a.vx * dt;
          a.oy += a.vy * dt;
          const limit = 18;
          a.ox = Math.max(-limit, Math.min(limit, a.ox));
          a.oy = Math.max(-limit, Math.min(limit, a.oy));
          if (Math.abs(a.ox) >= limit) a.vx *= -0.8;
          if (Math.abs(a.oy) >= limit) a.vy *= -0.8;
        } else if (it.type === 'worker') {
          a.ox = Math.sin(nowMs / 900 + a.phase) * 3;
          a.oy = Math.sin(nowMs / 700 + a.phase) * 2;
        } else if (it.type === 'gather') {
          a.oy = (it.gather && it.gather.ready) ? Math.sin(nowMs / 280 + a.phase) * 3 : 0;
        }
      });

      if (selected) {
        const item = interactables.find(it => it.id === selected.id);
        if (item && dist(player, itemPos(item)) < item.r + 28) showPanel(item);
      }
    }

    function loop(ts) {
      if (!lastTs) lastTs = ts;
      const dt = Math.min(0.05, (ts - lastTs) / 1000);
      lastTs = ts;
      update(dt);
      draw();
      raf = requestAnimationFrame(loop);
    }

    let pointerDown = false;
    function pickHit(pos) {
      return interactables.find(it => {
        if (it.type === 'plot') return pos.x >= it.x - it.w / 2 && pos.x <= it.x + it.w / 2 && pos.y >= it.y - it.h / 2 && pos.y <= it.y + it.h / 2;
        return dist(pos, itemPos(it)) < it.r;
      });
    }
    function pointTo(pos) {
      player.tx = pos.x; player.ty = pos.y;
      const hit = pickHit(pos);
      if (hit) {
        selected = hit;
        if (dist(player, itemPos(hit)) < hit.r + 28) showPanel(hit);
        else hidePanel();
      } else {
        selected = null;
        hidePanel();
      }
    }
    canvas.addEventListener('pointerdown', (evt) => {
      pointerDown = true;
      canvas.setPointerCapture(evt.pointerId);
      pointTo(toCanvasPos(evt));
    });
    canvas.addEventListener('pointermove', (evt) => {
      if (!pointerDown) return;
      const pos = toCanvasPos(evt);
      player.tx = pos.x; player.ty = pos.y;
    });
    canvas.addEventListener('pointerup', () => { pointerDown = false; });
    canvas.addEventListener('pointerleave', () => { pointerDown = false; });

    function ensureLoop() {
      if (!raf) raf = requestAnimationFrame(loop);
    }

    function updateFromFarm(data) {
      buildInteractables(data);
      ensureLoop();
      draw();
    }

    function getSelectedPlot() {
      if (!selected || selected.type !== 'plot') return null;
      return selected.plot ? selected.plot.index : null;
    }

    return { updateFromFarm, hidePanel, getSelectedPlot };
  })();

  // ---------------- 農場ゲーム ----------------
  function setView(view) {
    state.view = view;
    $('drill-view').classList.toggle('hidden', view !== 'drill');
    $('farm-view').classList.toggle('hidden', view !== 'farm');
    $('mode-drill').classList.toggle('selected', view === 'drill');
    $('mode-farm').classList.toggle('selected', view === 'farm');
    if (state.farmTimer) {
      clearInterval(state.farmTimer);
      state.farmTimer = null;
    }
    if (view === 'farm') {
      loadFarm();
      state.farmTimer = setInterval(() => {
        if (state.view === 'farm') loadFarm(true);
      }, 3000);
    }
  }

  function farmSignature(data) {
    const plots = data.plots.map((p) => `${p.index}:${p.crop || '-'}:${p.ready ? 1 : 0}`).join('|');
    const animals = data.animals.map((a) => `${a.id}:${a.ready ? 1 : 0}:${a.fullness || 0}`).join('|');
    const buildings = data.buildings.map((b) => `${b.key}:${b.count}`).join('|');
    const tools = (data.tools || []).map((t) => `${t.key}:${t.owned ? 1 : 0}`).join('|');
    const gathers = (data.gathers || []).map((g) => `${g.key}:${g.ready ? 1 : 0}:${g.locked ? 1 : 0}`).join('|');
    const workers = (data.workers || []).map((w) => `${w.key}:${w.hired ? 1 : 0}:${w.ready ? 1 : 0}`).join('|');
    const inventory = Object.entries(data.inventory || {}).map(([k, v]) => `${k}:${v}`).join('|');
    return [data.farm.unlocked_plots, data.farm.exp, data.account.wallet,
      data.expansion_cost, plots, animals, buildings, tools, gathers, workers, inventory].join('#');
  }

  // 生育中だけ表示を書き換え、ボタンの作り直しでクリックが消えないようにする
  function updateFarmDynamic(data) {
    data.plots.forEach((plot) => {
      if (!plot.unlocked || !plot.crop || plot.ready) return;
      const cell = document.querySelector(`.plot[data-plot="${plot.index}"]`);
      if (!cell) return;
      const label = cell.querySelector('.remaining');
      if (label) label.textContent = `あと ${plot.remaining} 秒`;
      const fill = cell.querySelector('.mini-bar > div');
      if (fill) fill.style.width = `${Math.round(plot.progress * 100)}%`;
    });
    data.animals.forEach((animal) => {
      const card = document.querySelector(`.farm-card[data-animal-id="${animal.id}"]`);
      if (!card) return;
      const desc = card.querySelector('.desc');
      if (!desc) return;
      const need = animal.fullness_need || 80;
      const fullness = Number(animal.fullness || 0);
      desc.textContent = `満腹度 ${fullness}% / ${need}%  ${animal.ready ? '（生産OK！）' : '（えさが必要）'}`;
    });
    (data.gathers || []).forEach((spot) => {
      const card = document.querySelector(`.farm-card[data-gather-key="${spot.key}"]`);
      if (!card) return;
      const desc = card.querySelector('.desc');
      if (!desc) return;
      desc.textContent = spot.ready
        ? `${spot.resource_name} を 集められます！`
        : `あと ${spot.remaining} 秒`;
    });
    (data.workers || []).forEach((worker) => {
      if (!worker.hired || worker.ready) return;
      const card = document.querySelector(`.farm-card[data-worker-key="${worker.key}"]`);
      if (!card) return;
      const desc = card.querySelector('.desc');
      if (!desc) return;
      desc.textContent = `はたらき中… あと ${worker.remaining} 秒`;
    });
  }

  async function loadFarm(silent = false) {
    if (!state.account) return;
    try {
      const data = await api(`/api/farm?account_id=${state.account.id}`);
      state.farm = data;
      syncAccount(data.account);
      if (silent && state.farmSignature === farmSignature(data)) {
        updateFarmDynamic(data);
      } else {
        renderFarm(data);
      }
      if (state.view === 'farm') farmGame.updateFromFarm(data);
    } catch (error) {
      if (!silent) console.error(error);
    }
  }

  function showFarmMessage(text) {
    const box = $('farm-message');
    if (!text) {
      box.classList.add('hidden');
      box.textContent = '';
      return;
    }
    box.textContent = text;
    box.classList.remove('hidden');
    clearTimeout(showFarmMessage._timer);
    showFarmMessage._timer = setTimeout(() => box.classList.add('hidden'), 5000);
  }

  async function farmPost(path, payload) {
    try {
      const data = await api(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      state.farm = data;
      syncAccount(data.account);
      renderFarm(data);
      if (data.event && data.event.message) showFarmMessage(`🎉 ${data.event.message}`);
    } catch (error) {
      alert(error.message);
    }
  }

  function renderStat(container, label, value) {
    const box = el('div', 'stat');
    box.appendChild(el('span', 'value', String(value)));
    box.appendChild(el('span', 'label', label));
    container.appendChild(box);
  }

  function renderFarm(data) {
    if (!data) return;
    const farm = data.farm;
    const accountId = state.account.id;

    const status = $('farm-status');
    status.innerHTML = '';
    renderStat(status, '使えるポイント', data.account.wallet);
    renderStat(status, '農場レベル', `Lv.${farm.level}`);
    renderStat(status, '畑', `${farm.unlocked_plots} / ${farm.max_plots}`);
    const hunger = Number(farm.hunger || 0);
    renderStat(status, '空腹度', `${hunger}%`);
    $('farm-exp-bar').style.width = `${farm.exp % 100}%`;
    $('hunger-text').textContent = `${hunger}%`;
    $('hunger-bar-fill').style.width = `${Math.min(100, hunger)}%`;
    $('hunger-bar-fill').style.background = hunger >= 90 ? '#e74c3c' : hunger >= 70 ? '#f39c12' : '#4caf50';

    const inventory = $('farm-inventory');
    inventory.innerHTML = '';
    (data.catalog.resources || []).forEach((res) => {
      const amount = (data.inventory || {})[res.key] || 0;
      renderStat(inventory, `${res.emoji} ${res.name}`, amount);
    });
    const feedSource = $('feed-source');
    const prevFeed = feedSource.value;
    feedSource.innerHTML = '';
    (data.catalog.resources || [])
      .filter((r) => r.category === 'food' && r.key !== 'feed' && (r.feed_value || 0) > 0)
      .forEach((r) => {
        const opt = document.createElement('option');
        opt.value = r.key;
        opt.textContent = `${r.emoji} ${r.name} → 飼料${r.feed_value}`;
        feedSource.appendChild(opt);
      });
    if ([...feedSource.options].some(o => o.value === prevFeed)) feedSource.value = prevFeed;
    const updateFeedInfo = () => {
      const r = (data.catalog.resources || []).find(x => x.key === feedSource.value);
      $('feed-convert-info').textContent = r ? `1個で飼料${r.feed_value}個` : '';
    };
    feedSource.onchange = updateFeedInfo;
    updateFeedInfo();

    const eatSource = $('eat-source');
    const prevEat = eatSource.value;
    eatSource.innerHTML = '';
    (data.catalog.resources || [])
      .filter((r) => r.category === 'food' && (r.eat_value || 0) > 0)
      .forEach((r) => {
        const opt = document.createElement('option');
        opt.value = r.key;
        opt.textContent = `${r.emoji} ${r.name}（空腹度-${r.eat_value}）`;
        eatSource.appendChild(opt);
      });
    if ([...eatSource.options].some(o => o.value === prevEat)) eatSource.value = prevEat;
    const updateEatInfo = () => {
      const r = (data.catalog.resources || []).find(x => x.key === eatSource.value);
      $('eat-info').textContent = r ? `1個で空腹度-${r.eat_value}` : '';
    };
    eatSource.onchange = updateEatInfo;
    updateEatInfo();

    const picker = $('seed-picker');
    picker.innerHTML = '';
    data.catalog.crops.forEach((crop) => {
      const button = el('button', 'seed' + (state.selectedCrop === crop.key ? ' selected' : ''));
      button.type = 'button';
      button.appendChild(document.createTextNode(
        `${crop.emoji} ${crop.name}（${crop.cost}pt・${crop.grow}秒・${resLabel(crop.resource)}+${crop.yield}）`
      ));
      button.addEventListener('click', () => {
        state.selectedCrop = crop.key;
        renderFarm(data);
      });
      picker.appendChild(button);
    });

    const grid = $('farm-grid');
    grid.innerHTML = '';
    data.plots.forEach((plot) => {
      const cell = el('div', 'plot' +
        (!plot.unlocked ? ' locked' : plot.ready ? ' ready' : plot.crop ? ' growing' : ''));
      cell.dataset.plot = String(plot.index);
      if (!plot.unlocked) {
        cell.textContent = '🔒 未開放';
      } else if (!plot.crop) {
        cell.textContent = '＋ たねを植える';
        cell.addEventListener('click', () => farmPost('/api/farm/plant', {
          account_id: accountId, plot: plot.index, crop: state.selectedCrop,
        }));
      } else {
        cell.appendChild(el('span', 'emoji', plot.emoji));
        if (plot.ready) {
          cell.appendChild(el('div', '', `収穫！ ${resLabel(plot.resource)}+${plot.yield || 0}`));
          cell.addEventListener('click', () => farmPost('/api/farm/harvest', {
            account_id: accountId, plot: plot.index,
          }));
        } else {
          cell.appendChild(el('div', 'remaining', `あと ${plot.remaining} 秒`));
          const bar = el('div', 'mini-bar');
          const fill = el('div');
          fill.style.width = `${Math.round(plot.progress * 100)}%`;
          bar.appendChild(fill);
          cell.appendChild(bar);
        }
      }
      grid.appendChild(cell);
    });

    const expand = $('farm-expand');
    if (data.expansion_cost === null) {
      expand.classList.add('hidden');
    } else {
      expand.classList.remove('hidden');
      expand.textContent = `畑を ひろげる（${data.expansion_cost} pt）`;
    }

    const animals = $('farm-animals');
    animals.innerHTML = '';
    const feedable = (data.catalog.resources || []).filter(r => ['vegetable','fruit','carrot','feed'].includes(r.key));
    data.animals.forEach((animal) => {
      const card = el('div', 'farm-card');
      card.dataset.animalId = String(animal.id);
      const title = animal.nickname ? `${animal.emoji} ${animal.nickname}（${animal.name}）` : `${animal.emoji} ${animal.name}`;
      card.appendChild(el('div', 'title', title));
      const personality = animal.personality_name ? `${animal.personality_emoji || ''} ${animal.personality_name}` : '';
      card.appendChild(el('div', 'meta', `${personality} ・ なかよし度 ${animal.bond ?? 0}`));
      const need = animal.fullness_need || 80;
      const fullness = Number(animal.fullness || 0);
      card.appendChild(el('div', 'desc', `満腹度 ${fullness}% / ${need}%  ${animal.ready ? '（生産OK！）' : '（えさが必要）'}`));
      const bar = el('div', 'mini-bar');
      const fill = el('div');
      fill.style.width = `${Math.min(100, fullness)}%`;
      fill.style.background = animal.ready ? '#4caf50' : '#ff9800';
      bar.appendChild(fill);
      card.appendChild(bar);
      if (animal.last_event) card.appendChild(el('div', 'event', `最近: ${animal.last_event}`));

      const feedRow = el('div', 'actions');
      const sel = document.createElement('select');
      feedable.forEach(r => {
        const opt = document.createElement('option');
        opt.value = r.key;
        const have = (data.inventory || {})[r.key] || 0;
        opt.textContent = `${r.emoji}${r.name}(${have})`;
        sel.appendChild(opt);
      });
      sel.style.padding = '6px'; sel.style.borderRadius = '8px';
      const feedBtn = el('button', 'small-btn');
      feedBtn.type = 'button';
      feedBtn.textContent = 'えさをあげる';
      feedBtn.addEventListener('click', () => farmPost('/api/farm/feed-animal', {
        account_id: accountId, animal_id: animal.id, resource: sel.value, amount: 1,
      }));
      feedRow.appendChild(sel);
      feedRow.appendChild(feedBtn);
      card.appendChild(feedRow);

      const button = el('button', 'small-btn' + (animal.ready ? ' sub' : ''));
      button.type = 'button';
      button.textContent = animal.ready ? `集める（${resLabel(animal.resource)}+${animal.yield}）` : `満腹度 ${need}% で生産`;
      button.disabled = !animal.ready;
      button.addEventListener('click', () => farmPost('/api/farm/collect-animal', {
        account_id: accountId, animal_id: animal.id,
      }));
      card.appendChild(button);
      animals.appendChild(card);
    });
    data.catalog.animals.forEach((animal) => {
      const card = el('div', 'farm-card');
      card.appendChild(el('div', 'title', `${animal.emoji} ${animal.name}`));
      card.appendChild(el('div', 'desc',
        `畑の収穫物をあげると満腹度UP。${animal.fullness_need || 80}%で ${animal.product_emoji}${animal.product}（${resLabel(animal.resource)}+${animal.yield}）`));
      card.appendChild(el('div', 'meta', '買うと 個性と なまえが つきます'));
      const button = el('button', 'small-btn');
      button.type = 'button';
      button.textContent = `買う（${animal.cost} pt）`;
      button.addEventListener('click', () => farmPost('/api/farm/buy-animal', {
        account_id: accountId, animal: animal.key,
      }));
      card.appendChild(button);
      animals.appendChild(card);
    });

    const gathers = $('farm-gathers');
    gathers.innerHTML = '';
    (data.gathers || []).forEach((spot) => {
      const card = el('div', 'farm-card' + (spot.locked ? ' locked' : ''));
      card.dataset.gatherKey = spot.key;
      card.appendChild(el('div', 'title', `${spot.emoji} ${spot.name}`));
      if (spot.locked) {
        card.appendChild(el('div', 'desc', `🔒 ${spot.required_tool_name || '道具'} が必要`));
      } else {
        card.appendChild(el('div', 'desc',
          spot.ready ? `${spot.resource_name} を 集められます！` : `あと ${spot.remaining} 秒`));
      }
      const button = el('button', 'small-btn' + (spot.ready ? ' sub' : ''));
      button.type = 'button';
      if (spot.locked) {
        button.textContent = `${spot.required_tool_name} が必要`;
        button.disabled = true;
      } else {
        button.textContent = spot.ready ? `集める（${spot.resource_name}+${spot.yield}）` : 'まだ 集められない';
        button.disabled = !spot.ready;
      }
      button.addEventListener('click', () => farmPost('/api/farm/gather', {
        account_id: accountId, spot: spot.key,
      }));
      card.appendChild(button);
      gathers.appendChild(card);
    });

    const workers = $('farm-workers');
    workers.innerHTML = '';
    const fmtRes = (obj) => Object.entries(obj || {}).map(([k, v]) => `${resLabel(k)}+${v}`).join(' / ');
    const fmtCost = (cost) => {
      if (typeof cost === 'number') return `${cost}pt`;
      const parts = [];
      if (cost && cost.points) parts.push(`${cost.points}pt`);
      Object.entries(cost || {}).forEach(([k, v]) => { if (k !== 'points') parts.push(`${resLabel(k)}${v}`); });
      return parts.join(' + ');
    };
    const metWorkers = data.workers || [];
    if (!metWorkers.length) {
      workers.appendChild(el('div', 'hint', 'まだ 出会った人はいません。ドリルで 学習すると 出会えることがあります。'));
    }
    metWorkers.forEach((worker) => {
      const card = el('div', 'farm-card');
      card.dataset.workerKey = worker.key;
      card.appendChild(el('div', 'title', `${worker.emoji} ${worker.name}（${worker.role}）`));
      card.appendChild(el('div', 'desc', worker.description));
      card.appendChild(el('div', 'meta', `仕事: ${worker.work_interval}秒ごとに ${fmtRes(worker.yield)}`));
      if (!worker.hired) {
        card.appendChild(el('div', 'meta', `雇うコスト: ${fmtCost(worker.hire_cost)}`));
        const button = el('button', 'small-btn');
        button.type = 'button';
        button.textContent = `雇う（${fmtCost(worker.hire_cost)}）`;
        button.addEventListener('click', () => farmPost('/api/farm/hire-worker', {
          account_id: accountId, worker_key: worker.key,
        }));
        card.appendChild(button);
      } else {
        const status = worker.ready ? '仕事完了！受け取れます' : `はたらき中… あと ${worker.remaining} 秒`;
        card.appendChild(el('div', 'desc', status));
        const button = el('button', 'small-btn' + (worker.ready ? ' sub' : ''));
        button.type = 'button';
        button.textContent = worker.ready ? `受け取る（${fmtRes(worker.yield)}）` : 'はたらき中';
        button.disabled = !worker.ready;
        button.addEventListener('click', () => farmPost('/api/farm/collect-worker', {
          account_id: accountId, worker_key: worker.key,
        }));
        card.appendChild(button);
      }
      workers.appendChild(card);
    });

    const toolsWrap = $('farm-tools');
    toolsWrap.innerHTML = '';
    (data.tools || []).forEach((tool) => {
      const card = el('div', 'farm-card' + (tool.owned ? ' owned' : tool.prereq_met ? '' : ' locked'));
      card.appendChild(el('div', 'title', `${tool.emoji} ${tool.name} ${tool.owned ? '✅' : `（G${tool.grade}）`}`));
      card.appendChild(el('div', 'desc', tool.description));
      card.appendChild(el('div', 'meta', `解放: ${tool.unlock_label || '—'}`));
      if (tool.prereq_name) card.appendChild(el('div', 'meta', `前提: ${tool.prereq_name}${tool.prereq_met ? ' OK' : ' 未取得'}`));
      if (!tool.owned) {
        card.appendChild(el('div', 'meta', `コスト: ${fmtCost(tool.cost)}`));
        const button = el('button', 'small-btn');
        button.type = 'button';
        button.disabled = !tool.prereq_met;
        button.textContent = tool.prereq_met ? `買う（${fmtCost(tool.cost)}）` : `前提: ${tool.prereq_name} が必要`;
        button.addEventListener('click', () => farmPost('/api/farm/buy-tool', {
          account_id: accountId, tool: tool.key,
        }));
        card.appendChild(button);
      } else {
        // tool actions
        (tool.unlocks || []).forEach((action) => {
          if (action === 'mine_coal' || action === 'mine_iron') return; // gather unlocks, no button
          const btn = el('button', 'small-btn sub');
          btn.type = 'button';
          if (action === 'water_crop') {
            btn.textContent = '水やりする（選択中の畑）';
            btn.addEventListener('click', () => {
              const plot = farmGame.getSelectedPlot();
              if (plot === null || plot === undefined) { alert('畑マップで水やりしたい畑を選んでください'); return; }
              farmPost('/api/farm/tool-action', { account_id: accountId, action, plot });
            });
          } else if (action === 'chop_bonus') {
            btn.textContent = '木材ボーナス採集（木材+4）';
            btn.addEventListener('click', () => farmPost('/api/farm/tool-action', { account_id: accountId, action }));
          } else if (action === 'craft_bundle') {
            btn.textContent = '資材加工（木材3+石2→鉄1）';
            btn.addEventListener('click', () => farmPost('/api/farm/tool-action', { account_id: accountId, action }));
          } else {
            btn.textContent = tool.unlock_label || action;
            btn.addEventListener('click', () => farmPost('/api/farm/tool-action', { account_id: accountId, action }));
          }
          card.appendChild(btn);
        });
      }
      toolsWrap.appendChild(card);
    });

    const buildings = $('farm-buildings');
    buildings.innerHTML = '';
    const owned = {};
    data.buildings.forEach((building) => { owned[building.key] = building.count; });
    data.catalog.buildings.forEach((building) => {
      const card = el('div', 'farm-card');
      card.appendChild(el('div', 'title', `${building.emoji} ${building.name}${owned[building.key] ? ` × ${owned[building.key]}` : ''}`));
      card.appendChild(el('div', 'desc', building.description));
      card.appendChild(el('div', 'meta', `コスト: ${fmtCost(building.cost)}`));
      const button = el('button', 'small-btn');
      button.type = 'button';
      button.textContent = `建てる（${fmtCost(building.cost)}）`;
      button.addEventListener('click', () => farmPost('/api/farm/buy-building', {
        account_id: accountId, building: building.key,
      }));
      card.appendChild(button);
      buildings.appendChild(card);
    });
    state.farmSignature = farmSignature(data);
    farmGame.updateFromFarm(data);
  }

  async function init() {
    try {
      state.cfg = await api('/api/config');
      state.accounts = await api('/api/accounts');
      renderFilters();
      renderAccounts();
      const remembered = Number(localStorage.getItem('study_account_id'));
      const target = state.accounts.find((item) => item.id === remembered) || state.accounts[0];
      if (target) await selectAccount(target.id, { trusted: true });
    } catch (error) {
      alert('設定の読み込みに失敗しました: ' + error.message);
    }
  }

  $('start').addEventListener('click', startQuiz);
  $('again').addEventListener('click', startQuiz);
  $('back').addEventListener('click', () => { show('setup'); loadProgress(); loadAnalysis(); });
  $('quit').addEventListener('click', () => { show('setup'); loadProgress(); loadAnalysis(); });
  $('count').addEventListener('change', (e) => { state.count = Number(e.target.value); });
  $('difficulty').addEventListener('change', (e) => { state.difficulty = e.target.value; });
  $('submit').addEventListener('click', () => submitAnswer($('answer-input').value));
  $('answer-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') submitAnswer($('answer-input').value);
  });
  $('next').addEventListener('click', () => {
    state.index += 1;
    if (state.index < state.questions.length) renderQuestion();
    else showResult();
  });
  $('clear-progress').addEventListener('click', async () => {
    if (!state.account) return;
    if (!confirm('このアカウントの 記録と ポイントを 全部 消しますか？')) return;
    await api(`/api/progress?account_id=${state.account.id}`, { method: 'DELETE' });
    await loadProgress();
    await loadAnalysis();
  });

  $('account-login').addEventListener('click', () => {
    selectAccount(Number($('account-select').value));
  });
  $('account-new').addEventListener('click', () => {
    $('account-form').classList.toggle('hidden');
    $('new-nickname').focus();
  });
  $('create-account').addEventListener('click', createAccount);
  $('account-delete').addEventListener('click', deleteAccount);

  $('adaptive').addEventListener('change', (e) => { state.adaptive = e.target.checked; });
  $('refresh-analysis').addEventListener('click', () => loadAnalysis());

  $('mode-drill').addEventListener('click', () => setView('drill'));
  $('mode-farm').addEventListener('click', () => setView('farm'));
  $('go-study-room').addEventListener('click', () => setView('drill'));
  $('go-farm-room').addEventListener('click', () => setView('farm'));
  $('farm-refresh').addEventListener('click', () => loadFarm());
  $('farm-expand').addEventListener('click', () => {
    farmPost('/api/farm/expand', { account_id: state.account.id });
  });
  $('feed-convert-btn').addEventListener('click', () => {
    if (!state.account) return;
    const resource = $('feed-source').value;
    const amount = Number($('feed-amount').value || 1);
    farmPost('/api/farm/convert-feed', { account_id: state.account.id, resource, amount });
  });
  $('eat-btn').addEventListener('click', () => {
    if (!state.account) return;
    const resource = $('eat-source').value;
    const amount = Number($('eat-amount').value || 1);
    farmPost('/api/farm/eat', { account_id: state.account.id, resource, amount });
  });

  init();
  setView('drill');
})();

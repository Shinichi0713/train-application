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
    const animals = data.animals.map((a) => `${a.id}:${a.ready ? 1 : 0}`).join('|');
    const buildings = data.buildings.map((b) => `${b.key}:${b.count}`).join('|');
    return [data.farm.unlocked_plots, data.farm.exp, data.account.wallet,
      data.expansion_cost, plots, animals, buildings].join('#');
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
      desc.textContent = animal.ready
        ? `${animal.product_emoji} ${animal.product} が とれます！`
        : `あと ${animal.remaining} 秒`;
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
    } catch (error) {
      if (!silent) console.error(error);
    }
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
    $('farm-exp-bar').style.width = `${farm.exp % 100}%`;

    const picker = $('seed-picker');
    picker.innerHTML = '';
    data.catalog.crops.forEach((crop) => {
      const button = el('button', 'seed' + (state.selectedCrop === crop.key ? ' selected' : ''));
      button.type = 'button';
      button.appendChild(document.createTextNode(`${crop.emoji} ${crop.name}（${crop.cost}pt・${crop.grow}秒）`));
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
        const crop = data.catalog.crops.find((item) => item.key === plot.crop);
        if (plot.ready) {
          cell.appendChild(el('div', '', `収穫！ +${crop ? crop.sell : 0} pt`));
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
    data.animals.forEach((animal) => {
      const card = el('div', 'farm-card');
      card.dataset.animalId = String(animal.id);
      card.appendChild(el('div', 'title', `${animal.emoji} ${animal.name}`));
      card.appendChild(el('div', 'desc',
        animal.ready ? `${animal.product_emoji} ${animal.product} が とれます！` : `あと ${animal.remaining} 秒`));
      const button = el('button', 'small-btn' + (animal.ready ? ' sub' : ''));
      button.type = 'button';
      button.textContent = animal.ready ? 'とる' : 'まだ とれない';
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
      card.appendChild(el('div', 'desc', `${animal.product_emoji} ${animal.product} が ${animal.interval} 秒ごとに とれる`));
      const button = el('button', 'small-btn');
      button.type = 'button';
      button.textContent = `買う（${animal.cost} pt）`;
      button.addEventListener('click', () => farmPost('/api/farm/buy-animal', {
        account_id: accountId, animal: animal.key,
      }));
      card.appendChild(button);
      animals.appendChild(card);
    });

    const buildings = $('farm-buildings');
    buildings.innerHTML = '';
    const owned = {};
    data.buildings.forEach((building) => { owned[building.key] = building.count; });
    data.catalog.buildings.forEach((building) => {
      const card = el('div', 'farm-card');
      card.appendChild(el('div', 'title', `${building.emoji} ${building.name}${owned[building.key] ? ` × ${owned[building.key]}` : ''}`));
      card.appendChild(el('div', 'desc', building.description));
      const button = el('button', 'small-btn');
      button.type = 'button';
      button.textContent = `買う（${building.cost} pt）`;
      button.addEventListener('click', () => farmPost('/api/farm/buy-building', {
        account_id: accountId, building: building.key,
      }));
      card.appendChild(button);
      buildings.appendChild(card);
    });
    state.farmSignature = farmSignature(data);
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
  $('back').addEventListener('click', () => { show('setup'); loadProgress(); });
  $('quit').addEventListener('click', () => { show('setup'); loadProgress(); });
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

  $('mode-drill').addEventListener('click', () => setView('drill'));
  $('mode-farm').addEventListener('click', () => setView('farm'));
  $('farm-refresh').addEventListener('click', () => loadFarm());
  $('farm-expand').addEventListener('click', () => {
    farmPost('/api/farm/expand', { account_id: state.account.id });
  });

  init();
  setView('drill');
})();

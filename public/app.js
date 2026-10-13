const $ = id => document.getElementById(id);
let currentFact, category = '', requestNumber = 0;
async function get(path) { const response = await fetch(path); if (!response.ok) throw new Error('Could not load the catalogue.'); return response.json(); }
function link(element, url) { const parsed = new URL(url); if (parsed.protocol !== 'https:') throw new Error('Invalid source link'); element.href = parsed.href; }
async function shuffle() {
  $('shuffle').disabled = true;
  try {
    currentFact = await get('/api/random' + (category ? '?category=' + encodeURIComponent(category) : ''));
    if (!currentFact) throw new Error('No reviewed facts in this topic yet.');
    $('fact').textContent = currentFact.text; $('category').textContent = currentFact.category.toUpperCase();
    link($('source'), currentFact.source); $('source').textContent = currentFact.source_title + ' ↗';
    $('image').hidden = true; $('credit').hidden = true; $('placeholder').hidden = false;
    if (currentFact.image && currentFact.image_credit) {
      $('image').onload = () => { $('image').hidden = false; $('placeholder').hidden = true; $('credit').hidden = false; };
      $('image').onerror = () => { $('image').hidden = true; $('placeholder').hidden = false; $('credit').hidden = true; };
      link($('credit'),currentFact.image_credit); $('image').src = currentFact.image;
    }
    $('feedback').textContent = 'A fresh discovery, every time.';
  } catch(error) { $('feedback').textContent = error.message; }
  finally { $('shuffle').disabled = false; }
}
async function library() {
  const number = ++requestNumber;
  try {
    const facts = await get('/api/facts?' + new URLSearchParams({q:$('search').value,category}));
    if (number !== requestNumber) return;
    $('result-count').textContent = facts.length + ' discoveries'; $('cards').replaceChildren();
    for (const fact of facts) {
      const card = document.createElement('article'); card.className = 'card';
      const label = document.createElement('span'); label.className = 'eyebrow'; label.textContent = fact.category.toUpperCase();
      const text = document.createElement('p'); text.textContent = fact.text;
      const source = document.createElement('a'); source.textContent = fact.source_title + ' ↗'; link(source,fact.source); source.target = '_blank'; source.rel = 'noopener noreferrer';
      card.append(label,text,source); $('cards').append(card);
    }
    if (!facts.length) $('result-count').textContent = 'No discoveries found. Try another search.';
  } catch(error) { $('result-count').textContent = error.message; }
}
$('shuffle').addEventListener('click',shuffle);
$('copy').addEventListener('click', async () => { if (!currentFact) return; try { await navigator.clipboard.writeText(currentFact.text + '\n' + currentFact.source); $('feedback').textContent = 'Fact and source copied.'; } catch { $('feedback').textContent = 'Copy is unavailable in this browser. Select the fact text to copy it.'; } });
let timer; $('search').addEventListener('input',() => { clearTimeout(timer); timer = setTimeout(library,200); });
async function start() {
  try {
    const status = await get('/api/status'); $('total').textContent = status.approved; $('topics').textContent = status.categories.length;
    $('slack-status').textContent = status.slack_configured ? 'Slack credentials configured' : 'Slack setup needed';
    for (const topic of ['',...status.categories]) {
      const button = document.createElement('button'); button.textContent = topic || 'All discoveries'; button.setAttribute('aria-pressed',topic === '' ? 'true' : 'false');
      button.addEventListener('click',() => { category = topic; for (const item of $('filters').children) item.setAttribute('aria-pressed',String(item === button)); library(); shuffle(); });
      $('filters').append(button);
    }
    await Promise.all([shuffle(),library()]);
  } catch(error) { $('fact').textContent = error.message; $('slack-status').textContent = 'Catalogue unavailable'; }
}
start();

/* Local operator review only. Exported decisions remain untrusted approval input. */
'use strict';
class ReviewModel {
  constructor(data) {
    this.data = data;
    this.rows = new Map(data.resources.map(row => [row.id, row]));
    this.selected = new Set();
    this.decisions = new Map();
  }
  select(id, selected) {
    if (!this.rows.has(id)) throw Error('Unknown draft resource');
    if (selected) this.selected.add(id); else this.selected.delete(id);
  }
  dependencies(id) {
    const row = this.rows.get(id);
    return [...new Set([...(row.requires || []), ...(row.endpoints || [])])];
  }
  includeDependencies() {
    const pending = [...this.selected];
    for (let index = 0; index < pending.length; index++) {
      for (const id of this.dependencies(pending[index])) {
        if (!this.rows.has(id)) throw Error('Source dependency is absent from this draft');
        if (!this.selected.has(id)) { this.selected.add(id); pending.push(id); }
      }
    }
  }
  classification(value) {
    const scope = this.data.scopes.find(row => row.id === value.scope);
    if (!this.data.categories.some(row => row.id === value.category) || value.category === 'category-0'
        || !scope || typeof value.secret !== 'boolean'
        || (value.category.startsWith('category-4') && scope.kind !== 'project')) {
      throw Error('Choose an existing information category, exact scope and explicit secret review');
    }
    return {category: value.category, scope: {id: scope.id, kind: scope.kind},
      project: scope.kind === 'project' ? scope.id : null, secret: value.secret};
  }
  apply(value, reviewed) {
    if (!this.selected.size || reviewed !== true) throw Error('Select records and confirm that you reviewed their current contents');
    const assignment = this.classification(value);
    for (const id of this.selected) this.decisions.set(id, {id, payload_sha256: this.rows.get(id).payload_sha256,
      ...structuredClone(assignment)});
  }
  issues() {
    const dependencies = new Set();
    let unreviewed = 0;
    for (const id of this.selected) {
      if (!this.decisions.has(id)) unreviewed++;
      for (const required of this.dependencies(id)) if (!this.selected.has(required)) dependencies.add(required);
    }
    return {unreviewed, dependencies: [...dependencies]};
  }
  export() {
    const issues = this.issues();
    if (!this.selected.size || issues.unreviewed || issues.dependencies.length) {
      throw Error('Every selected record and source dependency must be included and explicitly classified');
    }
    return {schema_version: 1, draft_revision: this.data.draft_revision,
      organization_revision: this.data.organization_revision,
      resources: [...this.selected].sort().map(id => structuredClone(this.decisions.get(id)))};
  }
  filter(query, kind) {
    const normalize = text => text.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase();
    const terms = normalize(query).split(/\s+/).filter(Boolean);
    return this.data.resources.filter(row => (!kind || row.kind === kind)
      && terms.every(term => normalize(JSON.stringify([row.kind, row.provenance.identity, row.data])).includes(term)));
  }
}

function mountReview(data) {
  const model = new ReviewModel(data);
  const $ = id => document.getElementById(id);
  const text = (tag, value, className) => {
    const node = document.createElement(tag); node.textContent = value;
    if (className) node.className = className;
    return node;
  };
  const title = row => row.data.title || row.data.label || row.provenance.identity;
  const sourceLabel = row => /^[a-f0-9]{64}$/.test(row.provenance.identity)
    ? row.provenance.identity.slice(0, 12) : row.provenance.identity;
  $('organization').textContent = data.organization;
  $('revision').textContent = 'Draft ' + data.draft_revision.slice(0, 12);
  for (const [element, rows, placeholder] of [
    [$('category'), data.categories, 'Choose category'], [$('scope'), data.scopes, 'Choose scope'],
    [$('kind'), [...new Set(data.resources.map(row => row.kind))].sort().map(id => ({id, label: id})), 'All resource types']]) {
    element.append(new Option(placeholder, ''));
    for (const row of rows) element.append(new Option(row.label || row.id, row.id));
  }
  let focused = null;
  function inspect(row) {
    focused = row.id;
    $('detail-title').textContent = title(row);
    $('detail').textContent = JSON.stringify({kind: row.kind, source: row.provenance,
      data: row.data, dependencies: model.dependencies(row.id).map(id => ({id,
        title: model.rows.get(id)?.data.title || model.rows.get(id)?.provenance.identity || 'Missing source'}))}, null, 2);
  }
  function render() {
    const rows = model.filter($('search').value, $('kind').value);
    const body = $('records'); body.replaceChildren();
    for (const row of rows) {
      const tr = document.createElement('tr');
      const selection = document.createElement('input'); selection.type = 'checkbox';
      selection.checked = model.selected.has(row.id);
      selection.setAttribute('aria-label', 'Select ' + title(row));
      selection.addEventListener('change', () => {model.select(row.id, selection.checked); $('reviewed').checked = false; render();});
      const cell = document.createElement('td'); cell.append(selection); tr.append(cell);
      const titleCell = document.createElement('td');
      const open = text('button', title(row), 'record-title');
      open.type = 'button'; open.addEventListener('click', () => inspect(row)); titleCell.append(open);
      titleCell.append(text('small', row.provenance.collection + ' / ' + sourceLabel(row))); tr.append(titleCell);
      tr.append(text('td', row.kind));
      const decision = model.decisions.get(row.id);
      tr.append(text('td', decision ? decision.category + ' · ' + decision.scope.id + (decision.secret ? ' · secret' : '') : 'Needs review', decision ? 'classified' : 'pending'));
      body.append(tr);
    }
    const issues = model.issues();
    $('summary').textContent = `${model.selected.size} selected · ${issues.unreviewed} need classification · ${issues.dependencies.length} missing source dependencies`;
    $('visible-count').textContent = `${rows.length} of ${data.resources.length} draft records`;
    $('download').disabled = !model.selected.size || !!issues.unreviewed || !!issues.dependencies.length;
    if (focused && model.rows.has(focused)) inspect(model.rows.get(focused));
  }
  function act(callback) {
    try { callback(); $('message').textContent = ''; render(); }
    catch (error) { $('message').textContent = error.message; }
  }
  $('search').addEventListener('input', render); $('kind').addEventListener('change', render);
  $('select-visible').addEventListener('click', () => act(() => {
    for (const row of model.filter($('search').value, $('kind').value)) model.select(row.id, true);
    $('reviewed').checked = false;
  }));
  $('clear').addEventListener('click', () => act(() => {model.selected.clear(); $('reviewed').checked = false;}));
  $('dependencies').addEventListener('click', () => act(() => {model.includeDependencies(); $('reviewed').checked = false;}));
  for (const id of ['category', 'scope', 'secret']) $(id).addEventListener('change', () => {$('reviewed').checked = false;});
  $('apply').addEventListener('click', () => act(() => {
    const secret = $('secret').value;
    model.apply({category: $('category').value, scope: $('scope').value,
      secret: secret === 'yes' ? true : secret === 'no' ? false : null}, $('reviewed').checked);
    $('reviewed').checked = false;
  }));
  $('download').addEventListener('click', () => act(() => {
    const blob = new Blob([JSON.stringify(model.export(), null, 2) + '\n'], {type: 'application/json'});
    const url = URL.createObjectURL(blob); const link = document.createElement('a');
    link.href = url; link.download = 'projection-decisions-' + data.draft_revision.slice(0, 12) + '.json';
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }));
  $('coverage').textContent = 'Outside this review: ' + data.unsupported.join(', ') + '. Omitted candidates: ' + data.omitted_count + '.';
  render();
}

if (typeof module !== 'undefined' && module.exports) module.exports = {ReviewModel};
else mountReview(JSON.parse(document.getElementById('review-data').textContent));

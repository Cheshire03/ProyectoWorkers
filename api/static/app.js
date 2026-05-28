const API = ''

// ── Estado local ──────────────────────────────────────────────────────────────
const state = {
  tasks: {},
  workers: [],
  selectedFiles: [],
}

// ── Navegación ────────────────────────────────────────────────────────────────
function showSection(name, el) {
  document.querySelectorAll('section[id^="section-"]').forEach(s => s.style.display = 'none')
  document.getElementById('section-' + name).style.display = 'block'
  document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'))
  if (el) el.classList.add('active')
  if (name === 'workers') renderWorkersSection()
  if (name === 'tareas')  renderTasksTable2()
}

// ── Upload ────────────────────────────────────────────────────────────────────
function onFileSelected(input) {
  addFiles(Array.from(input.files))
  input.value = ''
}

function addFiles(files) {
  const csvFiles = files.filter(f => f.name.endsWith('.csv'))
  csvFiles.forEach(f => {
    if (!state.selectedFiles.find(sf => sf.name === f.name)) {
      state.selectedFiles.push(f)
    }
  })
  renderFileList()
  document.getElementById('btn-submit').disabled = state.selectedFiles.length === 0
}

function removeFile(index) {
  state.selectedFiles.splice(index, 1)
  renderFileList()
  document.getElementById('btn-submit').disabled = state.selectedFiles.length === 0
}

function renderFileList() {
  const list = document.getElementById('file-list')
  const zone = document.getElementById('upload-zone')

  if (state.selectedFiles.length === 0) {
    zone.classList.remove('has-file')
    document.getElementById('upload-text').textContent = 'Arrastra tus CSVs aquí'
    document.getElementById('upload-hint').textContent = 'o haz click para seleccionar (puedes subir varios)'
    list.innerHTML = ''
    list.style.display = 'none'
    return
  }

  zone.classList.add('has-file')
  document.getElementById('upload-text').textContent = `${state.selectedFiles.length} archivo${state.selectedFiles.length > 1 ? 's' : ''} seleccionado${state.selectedFiles.length > 1 ? 's' : ''}`
  document.getElementById('upload-hint').textContent = 'Se procesarán en paralelo'

  list.style.display = 'block'
  list.innerHTML = state.selectedFiles.map((f, i) => `
    <div class="file-item">
      <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
      <span class="file-name">${f.name}</span>
      <span class="file-size">${(f.size/1024).toFixed(1)} KB</span>
      <button class="file-remove" onclick="removeFile(${i})" title="Quitar">✕</button>
    </div>
  `).join('')
}

// Drag & drop
const zone = document.getElementById('upload-zone')
zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over') })
zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'))
zone.addEventListener('drop', e => {
  e.preventDefault()
  zone.classList.remove('drag-over')
  addFiles(Array.from(e.dataTransfer.files))
})

function onOperationChange() {
  const op = document.getElementById('operation').value
  document.getElementById('params-filter').style.display = op === 'filter' ? 'block' : 'none'
  document.getElementById('params-sort').style.display   = op === 'sort'   ? 'block' : 'none'
}

// ── Submit task ───────────────────────────────────────────────────────────────
async function submitTask() {
  const op    = document.getElementById('operation').value
  const errEl = document.getElementById('submit-error')
  errEl.style.display = 'none'

  if (state.selectedFiles.length === 0) { showError(errEl, 'Selecciona al menos un archivo CSV.'); return }

  let params = {}
  if (op === 'filter') {
    params = {
      columna:  document.getElementById('filter-col').value.trim(),
      operador: document.getElementById('filter-op').value,
      valor:    document.getElementById('filter-val').value.trim(),
    }
    if (!params.columna || !params.valor) { showError(errEl, 'Completa columna y valor para filter.'); return }
  }
  if (op === 'sort') {
    params = {
      columna:    document.getElementById('sort-col').value.trim(),
      ascendente: document.getElementById('sort-dir').value === 'true',
    }
    if (!params.columna) { showError(errEl, 'Ingresa una columna para sort.'); return }
  }

  const btn = document.getElementById('btn-submit')
  btn.disabled = true
  btn.textContent = 'Enviando...'

  try {
    const fd = new FormData()
    state.selectedFiles.forEach(f => fd.append('files', f))
    fd.append('operation', op)
    fd.append('params', JSON.stringify(params))

    const res  = await fetch(API + '/tasks', { method: 'POST', body: fd })
    const data = await res.json()

    if (!res.ok) { showError(errEl, data.detail || 'Error al enviar la tarea.'); return }

    // Agregar todas las tareas al estado
    data.tasks.forEach(t => { state.tasks[t.task_id] = t })
    renderTasksTable()
    updateMetrics()

    // Reset form
    state.selectedFiles = []
    renderFileList()

  } catch (e) {
    showError(errEl, 'Error de conexión con la API.')
  } finally {
    btn.disabled = false
    btn.innerHTML = `<svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg> Enviar tarea`
  }
}

function showError(el, msg) {
  el.textContent = msg
  el.style.display = 'block'
}

// ── SSE ───────────────────────────────────────────────────────────────────────
function connectSSE() {
  const dot = document.getElementById('sse-dot')
  const lbl = document.getElementById('sse-label')
  const es  = new EventSource(API + '/sse/tasks')

  es.onopen = () => { dot.classList.add('connected'); lbl.textContent = 'Conectado' }

  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      if (!data.task_id) return
      state.tasks[data.task_id] = { ...state.tasks[data.task_id], ...data }
      renderTasksTable()
      renderTasksTable2()
      updateMetrics()
    } catch (_) {}
  }

  es.onerror = () => {
    dot.classList.remove('connected')
    lbl.textContent = 'Reconectando...'
    setTimeout(connectSSE, 3000)
    es.close()
  }
}

// ── Render tablas ─────────────────────────────────────────────────────────────
function renderTasksTable() {
  const tasks = Object.values(state.tasks).reverse()
  const tbody = document.getElementById('tasks-tbody')
  const empty = document.getElementById('tasks-empty')
  const wrap  = document.getElementById('tasks-table-wrap')

  if (tasks.length === 0) { empty.style.display = 'block'; wrap.style.display = 'none'; return }
  empty.style.display = 'none'; wrap.style.display = 'block'

  tbody.innerHTML = tasks.slice(0, 15).map(t => `
    <tr>
      <td title="${t.filename || ''}">${t.filename || '—'}</td>
      <td><span class="op-badge">${t.operation || '—'}</span></td>
      <td>${statusBadge(t.status)}</td>
      <td style="color:#8a9a6a;font-size:12px">${t.worker_id || '—'}</td>
      <td>${actionBtns(t)}</td>
    </tr>
  `).join('')
}

function renderTasksTable2() {
  const tasks = Object.values(state.tasks).reverse()
  const tbody = document.getElementById('tasks-tbody-2')
  const empty = document.getElementById('tasks-empty-2')
  const wrap  = document.getElementById('tasks-table-wrap-2')

  if (tasks.length === 0) { empty.style.display = 'block'; wrap.style.display = 'none'; return }
  empty.style.display = 'none'; wrap.style.display = 'block'

  tbody.innerHTML = tasks.map(t => `
    <tr>
      <td style="font-family:monospace;font-size:11px;color:#8a9a6a">${t.task_id ? t.task_id.slice(0,8) + '…' : '—'}</td>
      <td title="${t.filename || ''}">${t.filename || '—'}</td>
      <td><span class="op-badge">${t.operation || '—'}</span></td>
      <td>${statusBadge(t.status)}</td>
      <td style="color:#8a9a6a;font-size:12px">${t.worker_id || '—'}</td>
      <td>${actionBtns(t)}</td>
    </tr>
  `).join('')
}

function statusBadge(status) {
  const map = { pendiente: 'badge-pending', en_proceso: 'badge-processing', completada: 'badge-done', error: 'badge-error' }
  return `<span class="badge ${map[status] || 'badge-pending'}">${status || 'pendiente'}</span>`
}

function actionBtns(t) {
  if (t.status !== 'completada') return ''
  return `
    <div style="display:flex;gap:4px">
      <button class="btn-icon green" title="Ver resultado" onclick="viewResult('${t.task_id}')">
        <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
      </button>
      <button class="btn-icon" title="Descargar resultado" onclick="downloadResult('${t.task_id}')">
        <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
      </button>
    </div>`
}

// ── Ver resultado en modal ────────────────────────────────────────────────────
async function viewResult(taskId) {
  try {
    const res  = await fetch(API + '/tasks/' + taskId + '/result')
    const data = await res.json()
    document.getElementById('modal-title').textContent = 'Resultado — ' + (state.tasks[taskId]?.filename || taskId)
    document.getElementById('modal-content').textContent = JSON.stringify(data, null, 2)
    document.getElementById('result-modal').style.display = 'flex'
  } catch (e) {
    alert('Error obteniendo resultado.')
  }
}

// ── Descargar resultado como archivo ─────────────────────────────────────────
function downloadResult(taskId) {
  window.location.href = API + '/tasks/' + taskId + '/download'
}

function closeModal(e) {
  if (e.target.id === 'result-modal') document.getElementById('result-modal').style.display = 'none'
}

// ── Workers ───────────────────────────────────────────────────────────────────
async function fetchWorkers() {
  try {
    const res  = await fetch(API + '/workers')
    const data = await res.json()
    state.workers = data.workers || []
    renderWorkersSidebar()
    document.getElementById('m-workers').textContent = state.workers.filter(w => w.active).length
  } catch (_) {}
}

function renderWorkersSidebar() {
  const el    = document.getElementById('workers-list')
  const count = document.getElementById('workers-count')
  const active = state.workers.filter(w => w.active)

  if (state.workers.length === 0) {
    el.innerHTML = '<span class="workers-empty">Sin workers detectados</span>'
    count.textContent = ''
    return
  }
  el.innerHTML = active.map(w => `
    <div class="worker-chip">
      <div class="dot ${w.active ? 'dot-green' : 'dot-gray'}"></div>
      ${w.worker_id}
    </div>
  `).join('')
  count.textContent = `${active.length} de ${state.workers.length} workers activos`
}

function renderWorkersSection() {
  const grid = document.getElementById('workers-grid')
  if (state.workers.length === 0) {
    grid.innerHTML = '<p style="color:var(--text-muted);font-size:13px">No se detectaron workers.</p>'
    return
  }
  grid.innerHTML = state.workers.map(w => `
    <div class="worker-card">
      <div class="worker-card-header">
        <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>
        <span class="worker-card-id">${w.worker_id}</span>
        <span class="worker-status-badge ${w.status === 'busy' ? 'busy' : w.active ? 'idle' : 'unknown'}">
          ${w.status === 'busy' ? 'ocupado' : w.active ? 'libre' : 'inactivo'}
        </span>
      </div>
      <div class="worker-meta">Último heartbeat: ${w.last_seen}</div>
    </div>
  `).join('')
}

// ── Métricas ──────────────────────────────────────────────────────────────────
function updateMetrics() {
  const tasks = Object.values(state.tasks)
  document.getElementById('m-total').textContent      = tasks.length
  document.getElementById('m-done').textContent       = tasks.filter(t => t.status === 'completada').length
  document.getElementById('m-processing').textContent = tasks.filter(t => t.status === 'en_proceso').length
}

// ── Init ──────────────────────────────────────────────────────────────────────
connectSSE()
fetchWorkers()
setInterval(fetchWorkers, 10000)
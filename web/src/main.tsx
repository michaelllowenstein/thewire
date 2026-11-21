declare module '*.css' {
    const content: string;
    export default content;
}

type Project = { id: number; name: string; client: string };
type Session = { id: number; project: string; task: string; start: string; end: string | null };
type Log = { id: number; project: string; kind: string; body: string; created: string };
type DashboardReport = { total_hours: number };

const escapeHtml = (value: unknown) => String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');

async function getJson<T>(path: string): Promise<T> {
    const response = await fetch(path);
    if (!response.ok) throw Error(`${path} ${response.status}`);
    return response.json() as Promise<T>;
}

async function App() {
    const root = document.getElementById('root');
    if (!root) return;

    try {
        const [projects, sessions, logs, tools, report] = await Promise.all([
            getJson<Project[]>('/api/projects'),
            getJson<Session[]>('/api/sessions'),
            getJson<Log[]>('/api/worklogs'),
            getJson<Record<string, unknown>>('/api/tools'),
            getJson<DashboardReport>('/api/report'),
        ]);

        root.innerHTML = `
            <main>
            <header>
            <span class="logo">TW</span>
            <div>
            <h1>TheWire</h1>
            <p>Unified developer operations · v0.1</p>
            </div>
            </header>
            <section class="stats">
            <article><small>Projects</small><strong>${projects.length}</strong></article>
            <article><small>Completed hours</small><strong>${report.total_hours.toFixed(2)}</strong></article>
            <article><small>Active sessions</small><strong>${sessions.filter(session => !session.end).length}</strong></article>
            <article><small>Registered tools</small><strong>${Object.keys(tools).length}</strong></article>
            </section>
            <div class="cols">
            <section>
            <h2>Projects</h2>
            ${projects.map(project => `<article><b>${escapeHtml(project.name)}</b><small>${escapeHtml(project.client || 'Personal')}</small></article>`).join('')}
            <h2>Recent sessions</h2>
            ${sessions.slice(0, 10).map(session => `<article><b>${escapeHtml(session.project)}</b><p>${escapeHtml(session.task)}</p><small>${escapeHtml(session.start)} · ${session.end ? 'Completed' : 'Running'}</small></article>`).join('')}
            </section>
            <section>
            <h2>Worklogs and insights</h2>
            ${logs.slice(0, 10).map(log => `<article><b>${escapeHtml(log.project)} · ${escapeHtml(log.kind)}</b><p>${escapeHtml(log.body)}</p><small>${escapeHtml(log.created)}</small></article>`).join('')}
            <h2>Tool registry</h2>
            ${Object.keys(tools).map(name => `<article><b>${escapeHtml(name)}</b></article>`).join('')}
            </section>
            </div>
            <footer>Local read-only dashboard. Use the tw CLI to modify records.</footer>
            </main>`;
    } catch (error) {
        root.innerHTML = `<main><header><span class="logo">TW</span><div><h1>TheWire</h1><p>Unified developer operations · v0.1</p></div></header><p class="error">API unavailable: ${escapeHtml(String(error))}. Start the API on port 8765.</p></main>`;
    }
}

void App();

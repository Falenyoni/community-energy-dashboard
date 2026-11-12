import { useEffect, useState } from 'react';
import { checkHealth, checkDatabase, getSimulationStatus, startSimulation } from './api';
import Dashboard from './components/Dashboard';
import AdminOverview from './components/AdminOverview';
import './styles/palette.css';
import './App.css';

function App() {
  const [status, setStatus] = useState('checking');
  const [view, setView] = useState('household');
  const [simStatus, setSimStatus] = useState(null);
  const [simError, setSimError] = useState(null);
  const [simDate, setSimDate] = useState('2026-01-31');
  const [period, setPeriod] = useState('day');

  useEffect(() => {
    Promise.all([checkHealth(), checkDatabase()])
      .then(() => setStatus('ok'))
      .catch(() => setStatus('error'));
  }, []);

  useEffect(() => {
    // Polls regardless of whether a simulation is active -- this is how the
    // button picks up "already running" state too, e.g. after a page reload.
    let cancelled = false;
    const poll = () => getSimulationStatus().then((s) => { if (!cancelled) setSimStatus(s); }).catch(() => {});
    poll();
    const timer = setInterval(poll, 1500);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const simRunning = simStatus?.running ?? false;

  function handleSimulate() {
    setSimError(null);
    // Slower than the backend's own default (0.3s) so each interval is
    // actually visible while presenting, not just a blur of numbers.
    startSimulation({ date: simDate, interval_seconds: 0.6 })
      .then((res) => {
        if (!res.started) setSimError(res.detail);
      })
      .catch((err) => setSimError(err.message));
  }

  return (
    <>
      <nav className="view-switcher">
        <button type="button" onClick={() => setView('household')} disabled={view === 'household'}>
          My Dashboard
        </button>
        <button type="button" onClick={() => setView('admin')} disabled={view === 'admin'}>
          Admin: All Households
        </button>
        <label className="simulate-date">
          Day to simulate
          <input
            type="date"
            min="2026-01-31"
            value={simDate}
            disabled={simRunning}
            onChange={(e) => setSimDate(e.target.value)}
          />
        </label>
        <button type="button" onClick={handleSimulate} disabled={simRunning} className="simulate-button">
          {simRunning
            ? `● Simulating ${simStatus.date}... ${simStatus.interval_index}/${simStatus.total_intervals}`
            : '▶ Simulate Community Day'}
        </button>
      </nav>
      {simError && <p className="simulate-error">Couldn't start simulation: {simError}</p>}
      {simStatus?.error && <p className="simulate-error">Last simulation run failed: {simStatus.error}</p>}

      <nav className="period-switcher">
        <span>Show ranking, community comparison and breakdown for:</span>
        {['day', 'week', 'month'].map((p) => (
          <button key={p} type="button" onClick={() => setPeriod(p)} disabled={period === p}>
            {p === 'day' ? 'Latest day' : p === 'week' ? 'Last 7 days' : 'Last 30 days'}
          </button>
        ))}
      </nav>

      {view === 'household' ? (
        <Dashboard simRunning={simRunning} period={period} />
      ) : (
        <AdminOverview simRunning={simRunning} period={period} />
      )}

      <footer className="system-status">
        API/database status: {status === 'ok' ? '✅ connected' : status === 'checking' ? '⏳ checking...' : '❌ unreachable'}
      </footer>
    </>
  );
}

export default App;

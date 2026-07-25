import { useEffect, useState } from 'react';
import { API_URL, checkHealth, checkDatabase, getReadingCount } from './api';
import './App.css';

const initialState = { status: 'checking', detail: '' };

function StatusRow({ label, result }) {
  const icon = result.status === 'ok' ? '✅' : result.status === 'checking' ? '⏳' : '❌';
  return (
    <li>
      <span>{icon}</span> <strong>{label}:</strong> {result.status}
      {result.detail && <span className="detail"> — {result.detail}</span>}
    </li>
  );
}

function App() {
  const [apiHealth, setApiHealth] = useState(initialState);
  const [dbHealth, setDbHealth] = useState(initialState);
  const [readingCount, setReadingCount] = useState(null);

  const runChecks = () => {
    setApiHealth(initialState);
    setDbHealth(initialState);

    checkHealth()
      .then(() => setApiHealth({ status: 'ok', detail: '' }))
      .catch((err) => setApiHealth({ status: 'error', detail: err.message }));

    checkDatabase()
      .then(() => setDbHealth({ status: 'ok', detail: '' }))
      .catch((err) => setDbHealth({ status: 'error', detail: err.message }));
  };

  useEffect(runChecks, []);

  // Polls independently of runChecks so the count keeps climbing live during
  // a long-running ingestion, without needing a manual "Re-check" click.
  useEffect(() => {
    const poll = () => getReadingCount().then(setReadingCount).catch(() => {});
    poll();
    const interval = setInterval(poll, 3000);
    return () => clearInterval(interval);
  }, []);

  return (
    <section id="status-check">
      <h1>Community Energy Dashboard</h1>
      <p>Backend connectivity check — API URL: <code>{API_URL}</code></p>
      <ul>
        <StatusRow label="API server" result={apiHealth} />
        <StatusRow label="Database" result={dbHealth} />
      </ul>
      <p>
        Readings in database:{' '}
        <strong>{readingCount === null ? '…' : readingCount.toLocaleString()}</strong>
        <span className="detail"> (refreshes every 3s)</span>
      </p>
      <button type="button" onClick={runChecks}>
        Re-check
      </button>
    </section>
  );
}

export default App;

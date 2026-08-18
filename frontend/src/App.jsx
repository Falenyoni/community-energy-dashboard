import { useEffect, useState } from 'react';
import { checkHealth, checkDatabase } from './api';
import Dashboard from './components/Dashboard';
import AdminOverview from './components/AdminOverview';
import './styles/palette.css';
import './App.css';

function App() {
  const [status, setStatus] = useState('checking');
  const [view, setView] = useState('household');

  useEffect(() => {
    Promise.all([checkHealth(), checkDatabase()])
      .then(() => setStatus('ok'))
      .catch(() => setStatus('error'));
  }, []);

  return (
    <>
      <nav className="view-switcher">
        <button type="button" onClick={() => setView('household')} disabled={view === 'household'}>
          My Dashboard
        </button>
        <button type="button" onClick={() => setView('admin')} disabled={view === 'admin'}>
          Admin: All Households
        </button>
      </nav>

      {view === 'household' ? <Dashboard /> : <AdminOverview />}

      <footer className="system-status">
        API/database status: {status === 'ok' ? '✅ connected' : status === 'checking' ? '⏳ checking...' : '❌ unreachable'}
      </footer>
    </>
  );
}

export default App;

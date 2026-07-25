import { useEffect, useState } from 'react';
import { checkHealth, checkDatabase } from './api';
import Dashboard from './components/Dashboard';
import './styles/palette.css';
import './App.css';

function App() {
  const [status, setStatus] = useState('checking');

  useEffect(() => {
    Promise.all([checkHealth(), checkDatabase()])
      .then(() => setStatus('ok'))
      .catch(() => setStatus('error'));
  }, []);

  return (
    <>
      <Dashboard />
      <footer className="system-status">
        API/database status: {status === 'ok' ? '✅ connected' : status === 'checking' ? '⏳ checking...' : '❌ unreachable'}
      </footer>
    </>
  );
}

export default App;

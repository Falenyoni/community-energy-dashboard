import { useEffect, useState } from 'react';

const STORAGE_KEY = 'hideSimulatedData';

// Shared between Dashboard and AdminOverview so the preference is consistent
// across both views and survives a page reload.
export function useHideSimulated() {
  const [hideSimulated, setHideSimulated] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === 'true';
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, String(hideSimulated));
    } catch {
      // Private browsing / storage disabled - toggle still works for this session.
    }
  }, [hideSimulated]);

  return [hideSimulated, setHideSimulated];
}

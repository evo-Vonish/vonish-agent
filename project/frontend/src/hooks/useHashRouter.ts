import { useState, useEffect, useCallback } from 'react';

export function useHashRouter() {
  const getRoute = useCallback(() => {
    const hash = window.location.hash;
    if (hash.startsWith('#/')) {
      return hash.slice(1); // Remove the leading #
    }
    return '/';
  }, []);

  const [currentPath, setCurrentPath] = useState(getRoute);

  useEffect(() => {
    const handleHashChange = () => {
      setCurrentPath(getRoute());
    };

    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, [getRoute]);

  const navigate = useCallback((path: string) => {
    window.location.hash = path;
  }, []);

  return { currentPath, navigate };
}

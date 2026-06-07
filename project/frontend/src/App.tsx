import { useEffect } from 'react';
import { AgentIDEShell } from '@/components/layout';
import { useChatStore } from '@/stores/chatStore';

function App() {
  const initialize = useChatStore((state) => state.initialize);

  useEffect(() => {
    void initialize();
  }, [initialize]);

  return <AgentIDEShell />;
}

export default App;

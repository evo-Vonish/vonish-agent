import { useEffect } from 'react';
import { MainLayout } from '@/components/layout';
import { MessageStream } from '@/components/chat';
import { Composer } from '@/components/composer';
import ToolsPage from '@/pages/ToolsPage';
import { useHashRouter } from '@/hooks/useHashRouter';
import { useChatStore } from '@/stores/chatStore';

function ChatPage() {
  return (
    <MainLayout>
      <MessageStream className="flex-1" />
      <Composer />
    </MainLayout>
  );
}

function App() {
  const { currentPath } = useHashRouter();
  const initialize = useChatStore((state) => state.initialize);

  useEffect(() => {
    void initialize();
  }, [initialize]);

  return (
    <>
      {currentPath === '/tools' ? <ToolsPage /> : <ChatPage />}
    </>
  );
}

export default App;

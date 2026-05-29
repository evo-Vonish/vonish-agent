import { useState } from 'react';
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import Sidebar from '@/components/Sidebar';
import HomePage from '@/pages/HomePage';
import DocPage from '@/pages/DocPage';
import { FileText, ArrowUp } from 'lucide-react';

function ScrollToTop() {
  return (
    <button
      onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
      className="fixed bottom-6 right-6 p-2.5 bg-surface hover:bg-surface-hover 
                 border border-border rounded-lg text-text-muted hover:text-text 
                 shadow-lg transition-all z-30"
      title="回到顶部"
    >
      <ArrowUp className="w-4 h-4" />
    </button>
  );
}

function Footer() {
  return (
    <footer className="mt-16 pt-8 border-t border-border text-center text-sm text-text-dim pb-8">
      <div className="flex items-center justify-center gap-2 mb-2">
        <FileText className="w-4 h-4" />
        <span>vonish Agent Docs</span>
      </div>
      <p>基于项目文档自动生成 | 持续更新</p>
    </footer>
  );
}

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  const handleNavigate = (path: string) => {
    navigate(path);
    setSidebarOpen(false);
  };

  return (
    <div className="min-h-screen bg-bg">
      <Sidebar 
        isOpen={sidebarOpen} 
        onToggle={() => setSidebarOpen(!sidebarOpen)}
        onNavigate={handleNavigate}
      />

      {/* Main content */}
      <main className="lg:ml-64 min-h-screen">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-6 lg:py-10">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/:slug" element={<DocPage />} />
          </Routes>
          <Footer />
        </div>
      </main>

      <ScrollToTop />
    </div>
  );
}

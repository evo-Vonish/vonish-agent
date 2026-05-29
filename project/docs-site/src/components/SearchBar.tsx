import { useState, useRef, useEffect } from 'react';
import { Search, X } from 'lucide-react';
import { docs } from '@/data/docs';

interface SearchBarProps {
  onNavigate: (path: string) => void;
}

interface SearchResult {
  id: string;
  title: string;
  preview: string;
  path: string;
}

export default function SearchBar({ onNavigate }: SearchBarProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }

    const q = query.toLowerCase();
    const searchResults: SearchResult[] = [];

    Object.entries(docs).forEach(([key, doc]) => {
      const content = doc.content.toLowerCase();
      const title = doc.title.toLowerCase();

      if (title.includes(q) || content.includes(q)) {
        const index = content.indexOf(q);
        const start = Math.max(0, index - 60);
        const end = Math.min(doc.content.length, index + 100);
        const preview = doc.content.slice(start, end).replace(/[#*|\`]/g, '');

        searchResults.push({
          id: key,
          title: doc.title,
          preview: index >= 0 ? `...${preview}...` : preview,
          path: key === 'home' ? '/' : `/${key}`,
        });
      }
    });

    setResults(searchResults);
    setSelectedIndex(0);
  }, [query]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
        setIsOpen(true);
      }
      if (e.key === 'Escape') {
        setIsOpen(false);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % results.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 + results.length) % results.length);
    } else if (e.key === 'Enter' && results[selectedIndex]) {
      e.preventDefault();
      onNavigate(results[selectedIndex].path);
      setQuery('');
      setIsOpen(false);
    }
  };

  return (
    <div ref={containerRef} className="relative">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-dim" />
        <input
          ref={inputRef}
          type="text"
          placeholder="搜索文档..."
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
          }}
          onFocus={() => setIsOpen(true)}
          onKeyDown={handleKeyDown}
          className="w-full pl-9 pr-16 py-2 bg-surface border border-border rounded-lg 
                     text-sm text-text placeholder-text-dim 
                     focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/20
                     transition-all"
        />
        <kbd className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-text-dim 
                        bg-bg border border-border px-1.5 py-0.5 rounded hidden sm:inline-block">
          ⌘K
        </kbd>
      </div>

      {isOpen && query.trim() && (
        <div className="absolute top-full left-0 right-0 mt-2 bg-surface border border-border 
                        rounded-lg shadow-2xl overflow-hidden z-50">
          {results.length > 0 ? (
            <ul className="py-2 max-h-80 overflow-auto">
              {results.map((result, index) => (
                <li key={result.id}>
                  <button
                    onClick={() => {
                      onNavigate(result.path);
                      setQuery('');
                      setIsOpen(false);
                    }}
                    className={`w-full px-4 py-2.5 text-left transition-colors
                      ${index === selectedIndex ? 'bg-accent/10' : 'hover:bg-surface-hover'}`}
                  >
                    <div className="text-sm font-medium text-text">{result.title}</div>
                    <div className="text-xs text-text-dim mt-0.5 line-clamp-1">{result.preview}</div>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <div className="px-4 py-6 text-center text-sm text-text-dim">
              <X className="w-5 h-5 mx-auto mb-2 opacity-50" />
              未找到匹配的结果
            </div>
          )}
        </div>
      )}
    </div>
  );
}

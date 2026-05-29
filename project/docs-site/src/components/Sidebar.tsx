import { useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { ChevronDown, Menu, X, Cpu, FileText, Zap, Box, Database, Terminal, Layers, Code2, Rocket, HelpCircle, Home } from 'lucide-react';
import SearchBar from './SearchBar';
import { navigation } from '@/data/docs';

interface SidebarProps {
  isOpen: boolean;
  onToggle: () => void;
  onNavigate: (path: string) => void;
}

const iconMap: Record<string, React.ReactNode> = {
  'home': <Home className="w-4 h-4" />,
  'quickstart': <Zap className="w-4 h-4" />,
  'architecture': <Box className="w-4 h-4" />,
  'agent': <Cpu className="w-4 h-4" />,
  'agent-loop': <Cpu className="w-4 h-4" />,
  'models': <Layers className="w-4 h-4" />,
  'tools': <Terminal className="w-4 h-4" />,
  'context-os': <Database className="w-4 h-4" />,
  'workspace': <FileText className="w-4 h-4" />,
  'frontend': <Code2 className="w-4 h-4" />,
  'api': <Code2 className="w-4 h-4" />,
  'deployment': <Rocket className="w-4 h-4" />,
  'faq': <HelpCircle className="w-4 h-4" />,
};

function NavGroup({ item, onNavigate }: { item: typeof navigation[0]; onNavigate: (path: string) => void }) {
  const [expanded, setExpanded] = useState(true);
  const location = useLocation();
  const hasChildren = item.children && item.children.length > 0;
  const isActive = location.pathname === item.href;
  const isChildActive = hasChildren && item.children?.some(c => c.href === location.pathname);

  return (
    <div className="mb-1">
      <div className="flex items-center">
        {hasChildren ? (
          <button
            onClick={() => setExpanded(!expanded)}
            className={`flex items-center gap-2 flex-1 px-3 py-2 text-sm rounded-md transition-all
              ${isActive || isChildActive
                ? 'text-accent font-medium' 
                : 'text-text-muted hover:text-text hover:bg-surface-hover'
              }`}
          >
            <span className="text-text-dim">{iconMap[item.id] || <Box className="w-4 h-4" />}</span>
            <span className="flex-1 text-left">{item.label}</span>
            <ChevronDown 
              className={`w-3.5 h-3.5 text-text-dim transition-transform ${expanded ? '' : '-rotate-90'}`} 
            />
          </button>
        ) : (
          <NavLink
            to={item.href}
            onClick={() => onNavigate(item.href)}
            className={({ isActive }) => 
              `flex items-center gap-2 flex-1 px-3 py-2 text-sm rounded-md transition-all
              ${isActive 
                ? 'text-accent font-medium bg-accent/10' 
                : 'text-text-muted hover:text-text hover:bg-surface-hover'
              }`
            }
          >
            <span className="text-text-dim">{iconMap[item.id] || <Box className="w-4 h-4" />}</span>
            <span className="flex-1">{item.label}</span>
          </NavLink>
        )}
      </div>

      {hasChildren && expanded && (
        <div className="ml-4 mt-0.5 border-l border-border-light pl-2">
          {item.children?.map((child, idx) => (
            <NavLink
              key={`${child.id}-${idx}`}
              to={child.href}
              onClick={() => onNavigate(child.href)}
              className={({ isActive }) => 
                `block px-3 py-1.5 text-sm rounded-md transition-all
                ${isActive 
                  ? 'text-accent font-medium bg-accent/10' 
                  : 'text-text-dim hover:text-text hover:bg-surface-hover'
                }`
              }
            >
              {child.label}
            </NavLink>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Sidebar({ isOpen, onToggle, onNavigate }: SidebarProps) {
  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={onToggle}
        />
      )}

      {/* Toggle button - mobile */}
      <button
        onClick={onToggle}
        className="fixed top-4 left-4 z-50 lg:hidden p-2 bg-surface border border-border 
                   rounded-lg text-text-muted hover:text-text hover:bg-surface-hover transition-colors"
      >
        {isOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
      </button>

      {/* Sidebar */}
      <aside
        className={`fixed top-0 left-0 h-full w-64 bg-bg-secondary border-r border-border 
                    flex flex-col z-40 transition-transform duration-300 ease-in-out
                    ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}
      >
        {/* Logo */}
        <div className="px-4 py-5 border-b border-border">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-accent/15 flex items-center justify-center">
              <Cpu className="w-4.5 h-4.5 text-accent" />
            </div>
            <div>
              <h1 className="text-sm font-semibold text-text">vonish Agent</h1>
              <p className="text-[11px] text-text-dim">Documentation</p>
            </div>
          </div>
        </div>

        {/* Search */}
        <div className="px-4 py-3 border-b border-border">
          <SearchBar onNavigate={onNavigate} />
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto px-3 py-3">
          {navigation.map((item) => (
            <NavGroup key={item.id} item={item} onNavigate={onNavigate} />
          ))}
        </nav>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-border text-[11px] text-text-dim">
          <p>vonish Agent Docs v1.0</p>
        </div>
      </aside>
    </>
  );
}

import { useParams, useLocation } from 'react-router-dom';
import { useEffect } from 'react';
import Content from '@/components/Content';
import { docs } from '@/data/docs';

export default function DocPage() {
  const { slug } = useParams<{ slug?: string }>();
  const location = useLocation();
  
  const docKey = slug || 'home';
  const doc = docs[docKey];

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [location.pathname]);

  if (!doc) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
        <h1 className="text-4xl font-bold text-text mb-4">404</h1>
        <p className="text-text-muted mb-6">页面未找到</p>
        <a href="/" className="text-accent hover:underline">返回首页</a>
      </div>
    );
  }

  return <Content title={doc.title} content={doc.content} currentPath={location.pathname} />;
}

import { useLocation } from 'react-router-dom';
import { useEffect } from 'react';
import Content from '@/components/Content';
import { docs } from '@/data/docs';

export default function HomePage() {
  const location = useLocation();
  
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [location.pathname]);

  return <Content title={docs.home.title} content={docs.home.content} currentPath="/" />;
}

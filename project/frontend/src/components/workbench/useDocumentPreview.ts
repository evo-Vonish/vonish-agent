import { useEffect, useState } from 'react';
import { getDocumentPreview, type DocumentPreviewResult } from '@/services/api';

/** Fetches a structured document preview (pdf/docx/xlsx/pptx) for a workbench tab. */
export function useDocumentPreview(workspaceId: string | null | undefined, path: string | undefined) {
  const [data, setData] = useState<DocumentPreviewResult | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setData(null);
    if (!workspaceId || !path) {
      setLoading(false);
      return;
    }
    getDocumentPreview(workspaceId, path)
      .then((res) => {
        if (alive) {
          setData(res);
          setLoading(false);
        }
      })
      .catch(() => {
        if (alive) {
          setData({ success: false, error: { code: 'FETCH_FAILED', message: '加载文档预览失败' } });
          setLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [workspaceId, path]);

  return { data, loading };
}

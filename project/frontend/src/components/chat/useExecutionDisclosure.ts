import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

type DisclosureTone = 'neutral' | 'success' | 'failed' | 'interrupted';
type TitleMotion = 'idle' | 'running' | 'completed-flash';

interface UseExecutionDisclosureOptions {
  id: string;
  status: string;
  defaultExpanded?: boolean;
  defaultCollapsed?: boolean;
  runningStatuses?: string[];
  failedStatuses?: string[];
  interruptedStatuses?: string[];
  terminalStatuses?: string[];
}

interface UseExecutionDisclosureResult {
  expanded: boolean;
  userControlled: boolean;
  finishing: boolean;
  tone: DisclosureTone;
  titleMotion: TitleMotion;
  setExpanded: (expanded: boolean) => void;
  toggle: () => void;
}

const DEFAULT_RUNNING = ['running', 'streaming', 'retrying'];
const DEFAULT_FAILED = ['failed', 'error'];
const DEFAULT_INTERRUPTED = ['cancelled', 'interrupted'];
const DEFAULT_TERMINAL = ['completed', 'complete', 'success', 'failed', 'error', 'cancelled', 'interrupted', 'skipped'];

export function useExecutionDisclosure({
  id,
  status,
  defaultExpanded = false,
  defaultCollapsed,
  runningStatuses = DEFAULT_RUNNING,
  failedStatuses = DEFAULT_FAILED,
  interruptedStatuses = DEFAULT_INTERRUPTED,
  terminalStatuses = DEFAULT_TERMINAL,
}: UseExecutionDisclosureOptions): UseExecutionDisclosureResult {
  const runningKey = runningStatuses.join('|');
  const failedKey = failedStatuses.join('|');
  const interruptedKey = interruptedStatuses.join('|');
  const terminalKey = terminalStatuses.join('|');
  const isRunning = useMemo(() => runningStatuses.includes(status), [runningKey, status]);
  // Expansion is now strictly user-controlled. Running/completed status and
  // backend defaultCollapsed hints must not auto-open or auto-close cards.
  const initialExpanded = false;
  const [expanded, setExpandedState] = useState(initialExpanded);
  const [userControlled, setUserControlled] = useState(false);

  const previousIdRef = useRef(id);
  const userControlledRef = useRef(userControlled);

  useEffect(() => {
    userControlledRef.current = userControlled;
  }, [userControlled]);

  useEffect(() => {
    if (previousIdRef.current !== id) {
      previousIdRef.current = id;
      setUserControlled(false);
      userControlledRef.current = false;
      setExpandedState(false);
    }
  }, [defaultCollapsed, defaultExpanded, id]);

  const tone = useMemo<DisclosureTone>(() => {
    if (failedStatuses.includes(status)) return 'failed';
    if (interruptedStatuses.includes(status)) return 'interrupted';
    if (terminalStatuses.includes(status) && !isRunning) return 'success';
    return 'neutral';
  }, [failedKey, interruptedKey, isRunning, status, terminalKey]);

  const setExpanded = useCallback((next: boolean) => {
    setUserControlled(true);
    userControlledRef.current = true;
    setExpandedState(next);
  }, []);

  const toggle = useCallback(() => {
    setExpandedState((value) => {
      setUserControlled(true);
      userControlledRef.current = true;
      return !value;
    });
  }, []);

  const titleMotion: TitleMotion = isRunning
    ? 'running'
    : 'idle';

  return {
    expanded,
    userControlled,
    finishing: false,
    tone,
    titleMotion,
    setExpanded,
    toggle,
  };
}

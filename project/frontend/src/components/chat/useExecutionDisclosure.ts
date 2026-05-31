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

function collapseDelayForTone(tone: DisclosureTone) {
  if (tone === 'failed' || tone === 'interrupted') return 2200;
  if (tone === 'success') return 1250;
  return 0;
}

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
  const initialExpanded = isRunning || defaultExpanded || defaultCollapsed === false;
  const [expanded, setExpandedState] = useState(initialExpanded);
  const [userControlled, setUserControlled] = useState(false);
  const [finishing, setFinishing] = useState(false);

  const previousStatusRef = useRef(status);
  const previousIdRef = useRef(id);
  const userControlledRef = useRef(userControlled);
  const timersRef = useRef<number[]>([]);

  const clearTimers = useCallback(() => {
    timersRef.current.forEach((timer) => window.clearTimeout(timer));
    timersRef.current = [];
  }, []);

  useEffect(() => {
    userControlledRef.current = userControlled;
  }, [userControlled]);

  useEffect(() => {
    if (previousIdRef.current !== id) {
      clearTimers();
      previousIdRef.current = id;
      previousStatusRef.current = status;
      setUserControlled(false);
      userControlledRef.current = false;
      setFinishing(false);
      setExpandedState(isRunning || defaultExpanded || defaultCollapsed === false);
    }
  }, [clearTimers, defaultCollapsed, defaultExpanded, id, isRunning, status]);

  const tone = useMemo<DisclosureTone>(() => {
    if (failedStatuses.includes(status)) return 'failed';
    if (interruptedStatuses.includes(status)) return 'interrupted';
    if (terminalStatuses.includes(status) && !isRunning) return 'success';
    return 'neutral';
  }, [failedKey, interruptedKey, isRunning, status, terminalKey]);

  useEffect(() => {
    const previousStatus = previousStatusRef.current;
    const wasRunning = runningStatuses.includes(previousStatus);
    const nowRunning = runningStatuses.includes(status);
    const isTerminal = terminalStatuses.includes(status) && !nowRunning;

    if (nowRunning) {
      clearTimers();
      setFinishing(false);
      if (!userControlledRef.current) {
        setExpandedState(true);
      }
    } else if (wasRunning && isTerminal) {
      clearTimers();
      setFinishing(true);

      timersRef.current = [
        window.setTimeout(() => setFinishing(false), 850),
        window.setTimeout(() => {
          if (!userControlledRef.current) {
            setExpandedState(false);
          }
        }, collapseDelayForTone(tone)),
      ];
    }

    previousStatusRef.current = status;
    return clearTimers;
  }, [clearTimers, runningKey, status, terminalKey, tone]);

  const setExpanded = useCallback((next: boolean) => {
    clearTimers();
    setUserControlled(true);
    userControlledRef.current = true;
    setFinishing(false);
    setExpandedState(next);
  }, [clearTimers]);

  const toggle = useCallback(() => {
    setExpandedState((value) => {
      clearTimers();
      setUserControlled(true);
      userControlledRef.current = true;
      setFinishing(false);
      return !value;
    });
  }, [clearTimers]);

  const titleMotion: TitleMotion = isRunning
    ? 'running'
    : finishing
      ? 'completed-flash'
      : 'idle';

  return {
    expanded,
    userControlled,
    finishing,
    tone,
    titleMotion,
    setExpanded,
    toggle,
  };
}

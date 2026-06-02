import type { Message } from '@/types';

type TodoItem = { id: string; title: string; status: string; note?: string };
export type TodoSnapshot = { items: TodoItem[]; count: number };

function fromUnknown(raw: unknown): TodoSnapshot | null {
  if (!raw || typeof raw !== 'object') return null;
  const source = raw as Record<string, unknown>;
  if (!Array.isArray(source.items)) return null;
  const items = source.items
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'))
    .map((item) => ({
      id: String(item.id ?? ''),
      title: String(item.title ?? ''),
      status: String(item.status ?? 'todo'),
      note: item.note === undefined || item.note === null ? undefined : String(item.note),
    }))
    .filter((item) => item.title);
  return { items, count: Number(source.count ?? items.length) || items.length };
}

export function latestTodoFromMessages(messages: Message[]): TodoSnapshot | null {
  for (const message of [...messages].reverse()) {
    if (message.todo?.items?.length) return message.todo;
    for (const tool of [...(message.toolCalls ?? [])].reverse()) {
      if (tool.name === 'set_todo_list') {
        const todo = fromUnknown(tool.result);
        if (todo?.items.length) return todo;
      }
    }
    for (const segment of [...(message.segments ?? [])].reverse()) {
      if (segment.type === 'tool' && segment.tool.name === 'set_todo_list') {
        const todo = fromUnknown(segment.tool.result);
        if (todo?.items.length) return todo;
      }
      if (segment.type === 'execution') {
        for (const step of [...segment.execution.steps].reverse()) {
          if (step.toolName === 'set_todo_list' || step.metadata?.toolName === 'set_todo_list') {
            const todo = fromUnknown(step.metadata?.result);
            if (todo?.items.length) return todo;
          }
        }
      }
    }
  }
  return null;
}

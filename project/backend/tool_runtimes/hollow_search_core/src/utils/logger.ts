type LogLevel = 'debug' | 'info' | 'warn' | 'error';

const LEVEL_ORDER: Record<LogLevel, number> = {
  debug: 10,
  info: 20,
  warn: 30,
  error: 40,
};

export class Logger {
  constructor(
    private readonly namespace: string,
    private readonly minLevel: LogLevel = (process.env.LOG_LEVEL as LogLevel) || 'info',
  ) {}

  debug(message: string, meta?: unknown): void {
    this.write('debug', message, meta);
  }

  info(message: string, meta?: unknown): void {
    this.write('info', message, meta);
  }

  warn(message: string, meta?: unknown): void {
    this.write('warn', message, meta);
  }

  error(message: string, meta?: unknown): void {
    this.write('error', message, meta);
  }

  private write(level: LogLevel, message: string, meta?: unknown): void {
    if (LEVEL_ORDER[level] < LEVEL_ORDER[this.minLevel]) {
      return;
    }

    const line = `[${new Date().toISOString()}] ${level.toUpperCase()} ${this.namespace}: ${message}`;
    if (meta === undefined) {
      console[level === 'debug' ? 'log' : level](line);
    } else {
      console[level === 'debug' ? 'log' : level](line, meta);
    }
  }
}

export function createLogger(namespace: string): Logger {
  return new Logger(namespace);
}

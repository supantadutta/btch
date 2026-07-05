// WebSocket client with heartbeat-based staleness detection (docs/04).
// >45s without any server frame => 'stale'; auto-reconnect with backoff.
export type WsStatus = "connecting" | "live" | "stale" | "closed";

export class MarketSocket {
  private ws: WebSocket | null = null;
  private backoff = 1000;
  private lastFrame = Date.now();
  private timer: any;
  private handlers = new Map<string, Set<(d: any) => void>>();

  constructor(
    private url = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws",
    public onStatus: (s: WsStatus) => void = () => {},
    private channels: string[] = [],
  ) {}

  connect() {
    this.onStatus("connecting");
    try {
      this.ws = new WebSocket(this.url);
    } catch {
      return this.scheduleReconnect();
    }
    this.ws.onopen = () => {
      this.backoff = 1000;
      this.lastFrame = Date.now();
      this.onStatus("live");
      this.ws?.send(JSON.stringify({ op: "subscribe", channels: this.channels }));
    };
    this.ws.onmessage = (e) => {
      this.lastFrame = Date.now();
      const msg = JSON.parse(e.data);
      if (msg.ch === "heartbeat") return;
      this.handlers.get(msg.ch)?.forEach((h) => h(msg.data));
      this.handlers.get("*")?.forEach((h) => h(msg));
    };
    this.ws.onclose = () => this.scheduleReconnect();
    this.ws.onerror = () => this.ws?.close();
    this.timer = setInterval(() => {
      if (Date.now() - this.lastFrame > 45000) this.onStatus("stale");
    }, 5000);
  }

  on(channel: string, handler: (d: any) => void) {
    if (!this.handlers.has(channel)) this.handlers.set(channel, new Set());
    this.handlers.get(channel)!.add(handler);
    return () => this.handlers.get(channel)?.delete(handler);
  }

  private scheduleReconnect() {
    this.onStatus("closed");
    clearInterval(this.timer);
    setTimeout(() => this.connect(), this.backoff);
    this.backoff = Math.min(this.backoff * 2, 30000);
  }

  close() {
    clearInterval(this.timer);
    this.ws?.close();
  }
}

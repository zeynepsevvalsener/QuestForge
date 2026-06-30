export type GameStatus = "active" | "won" | "lost";

export interface InventoryItem {
  item: string;
  quantity: number;
}

export interface Room {
  id: string;
  name: string;
  description: string;
  exits: Record<string, string>;
  items: string[];
  enemy: string | null;
}

export interface Turn {
  id: number;
  role: "player" | "gm";
  content: string;
  tool_calls: ToolCallRecord[] | null;
  created_at: string;
}

export interface ToolCallRecord {
  tool: string;
  args: Record<string, unknown>;
  accepted: boolean;
  reason?: string;
  result?: string;
  [key: string]: unknown;
}

export interface GameState {
  id: number;
  status: GameStatus;
  hp: number;
  max_hp: number;
  location: string;
  room: Room;
  enemy_hp: number;
  inventory: InventoryItem[];
  alive: boolean;
  turns: Turn[];
}

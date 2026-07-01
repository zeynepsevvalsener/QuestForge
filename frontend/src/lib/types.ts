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
  action?: string;
  args?: Record<string, unknown>;
  ok?: boolean;
  message?: string;
  error?: string;
  events?: string[];
  // Legacy fields (older persisted turns).
  accepted?: boolean;
  reason?: string;
  result?: string;
  [key: string]: unknown;
}

export interface QuestStep {
  label: string;
  done: boolean;
}

export interface GameState {
  id: number;
  status: GameStatus;
  hp: number;
  max_hp: number;
  location: string;
  objective: string;
  progress: QuestStep[];
  room: Room;
  enemy_hp: number;
  enemy_max_hp: number;
  inventory: InventoryItem[];
  alive: boolean;
  turns: Turn[];
}

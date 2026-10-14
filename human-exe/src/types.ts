export interface Stats {
  health: number;
  intellect: number;
  charisma: number;
  luck: number;
  stress: number;
  reputation: number;
}
export interface Choice {
  text: string;
  result: string;
  effects?: Partial<Stats> & { money?: number; debt?: number };
  flags?: Record<string, number>;
  relationship?: number;
  job?: string;
  property?: string;
}
export interface GameEvent {
  id: string;
  title: string;
  description: string;
  category: string;
  minAge?: number;
  maxAge?: number;
  job?: string;
  property?: string;
  minMoney?: number;
  minReputation?: number;
  minBond?: number;
  romantic?: boolean;
  requires?: Record<string, number>;
  choices: Choice[];
}
export interface Relationship {
  name: string;
  bond: number;
  role: string;
  memory: string[];
}
export interface GameState {
  version: 1;
  seed: number;
  rng: number;
  age: number;
  turn: number;
  name: string;
  surname: string;
  city: string;
  money: number;
  stats: Stats;
  traits: string[];
  job: string | null;
  careerLevel: number;
  debt: number;
  properties: string[];
  relationships: Relationship[];
  flags: Record<string, number>;
  seen: string[];
  history: { age: number; title: string; text: string }[];
  achievements: string[];
  currentEvent: string;
  dead: boolean;
  ending: string | null;
  lastResult: string;
}
export interface Action {
  type:
    | "work"
    | "rest"
    | "study"
    | "social"
    | "job"
    | "buy"
    | "loan"
    | "repay"
    | "intimacy";
  id?: string;
  amount?: number;
}

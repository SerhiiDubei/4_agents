export interface CoreParameters {
  cooperationBias: number;
  deceptionTendency: number;
  strategicHorizon: number;
  riskAppetite: number;
}

export interface Answer {
  id: string;
  text: string;
  effects: Partial<CoreParameters>;
}

export interface Question {
  id: number;
  text: string;
  answers: Answer[];
  allowCustom?: boolean;
}

export interface Archetype {
  name: string;
  description: string;
  condition: (params: CoreParameters) => boolean;
}

export type GamePhase = 'intro' | 'questions' | 'reveal';
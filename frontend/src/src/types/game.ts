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

/** Step for configurable flow: story / question / reflection */
export interface QuestionStep {
  type: 'question';
  id: string;
  questionNumber: number;
  text: string;
  answers: Answer[];
  background: string;
  allowCustom?: boolean;
}

export interface StoryBeat {
  type: 'story';
  id: string;
  lines: string[];
  background: string;
}

export interface Reflection {
  type: 'reflection';
  id: string;
  text: string;
  background: string;
}

export type GameStep = QuestionStep | StoryBeat | Reflection;

export interface Archetype {
  name: string;
  description: string;
  condition: (params: CoreParameters) => boolean;
}

export type GamePhase = 'intro' | 'questions' | 'steps' | 'reveal';
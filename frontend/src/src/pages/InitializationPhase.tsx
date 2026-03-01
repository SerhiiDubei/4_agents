import React, { useMemo, useState, useEffect, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { GamePhase, CoreParameters, Answer, Archetype, Question } from '../types/game';
import {
  INITIAL_PARAMS,
  ARCHETYPES,
  getBackgroundClass,
} from '../data/questions';
import { IntroView } from '../components/IntroView';
import { QuestionView } from '../components/QuestionView';
import { RevealView } from '../components/RevealView';
import { CRTOverlay } from '../components/CRTOverlay';

type LoadingState = 'idle' | 'loading' | 'ready' | 'error';

export const InitializationPhase: React.FC = () => {
  const [phase, setPhase] = useState<GamePhase>('intro');
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [parameters, setParameters] = useState<CoreParameters>(INITIAL_PARAMS);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [sessionId, setSessionId] = useState<string>('');
  const [loadingState, setLoadingState] = useState<LoadingState>('idle');
  const [loadingError, setLoadingError] = useState<string>('');
  const [loadingSeconds, setLoadingSeconds] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const currentQuestion = questions[currentQuestionIndex];

  const backgroundClass =
    phase === 'questions' && currentQuestion
      ? getBackgroundClass(currentQuestion.id)
      : 'bg-game-black';

  const handleStart = async () => {
    setLoadingState('loading');
    setLoadingSeconds(0);
    timerRef.current = setInterval(() => setLoadingSeconds((s) => s + 1), 1000);
    try {
      const res = await fetch('/generate-game', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        const err = await res.text();
        throw new Error(err);
      }
      const data = await res.json();
      if (timerRef.current) clearInterval(timerRef.current);
      setSessionId(data.session_id);
      setQuestions(data.questions);
      setLoadingState('ready');
      setPhase('questions');
    } catch (e: unknown) {
      if (timerRef.current) clearInterval(timerRef.current);
      const msg = e instanceof Error ? e.message : String(e);
      setLoadingError(msg);
      setLoadingState('error');
    }
  };

  useEffect(() => () => { if (timerRef.current) clearInterval(timerRef.current); }, []);

  const handleAnswer = (answer: Answer) => {
    const newParams = { ...parameters };
    Object.entries(answer.effects).forEach(([key, value]) => {
      const paramKey = key as keyof CoreParameters;
      const currentValue = newParams[paramKey];
      let multiplier = 1;
      if (value > 0 && currentValue > 70) multiplier = 0.5;
      if (value < 0 && currentValue < 30) multiplier = 0.5;
      newParams[paramKey] = Math.max(0, Math.min(100, currentValue + value * multiplier));
    });
    setParameters(newParams);
    if (currentQuestionIndex < questions.length - 1) {
      setCurrentQuestionIndex((prev) => prev + 1);
    } else {
      setPhase('reveal');
    }
  };

  const determineArchetype = useMemo((): Archetype => {
    return (
      ARCHETYPES.find((a) => a.condition(parameters)) ||
      ARCHETYPES[ARCHETYPES.length - 1]
    );
  }, [parameters]);

  return (
    <div className={`min-h-screen w-full transition-colors duration-1000 ${backgroundClass}`}>
      <CRTOverlay />

      <AnimatePresence mode="wait">
        {phase === 'intro' && (
          <motion.div key="intro" className="absolute inset-0">
            <IntroView onStart={handleStart} />
            {loadingState === 'loading' && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="absolute inset-0 flex flex-col items-center justify-center bg-game-black/90 z-50">
                <div className="font-pixel text-game-cyan text-glow-cyan text-lg animate-pulse mb-4">
                  ІНІЦІАЛІЗАЦІЯ...
                </div>
                <div className="font-pixel text-game-lightGray/50 text-xs mb-1">
                  генерація особистості та питань
                </div>
                <div className="font-pixel text-game-lightGray/30 text-xs">
                  {loadingSeconds < 10
                    ? 'збір параметрів...'
                    : loadingSeconds < 30
                    ? 'формування ситуацій...'
                    : loadingSeconds < 60
                    ? 'фінальна обробка...'
                    : 'майже готово...'}
                  {' '}{loadingSeconds}s
                </div>
              </motion.div>
            )}
            {loadingState === 'error' && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="absolute bottom-16 left-0 right-0 flex justify-center z-50">
                <div className="bg-game-darkPurple border border-game-pink px-6 py-3 font-pixel text-game-pink text-sm">
                  ПОМИЛКА: {loadingError}
                </div>
              </motion.div>
            )}
          </motion.div>
        )}

        {phase === 'questions' && currentQuestion && (
          <motion.div
            key={`q-${currentQuestionIndex}`}
            className="absolute inset-0">
            <QuestionView
              question={currentQuestion}
              totalQuestions={questions.length}
              onAnswer={handleAnswer} />
          </motion.div>
        )}

        {phase === 'reveal' && (
          <motion.div key="reveal" className="absolute inset-0">
            <RevealView
              parameters={parameters}
              archetype={determineArchetype}
              sessionId={sessionId} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
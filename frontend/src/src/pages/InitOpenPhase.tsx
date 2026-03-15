import React, { useState, useCallback } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { OpenQuestionView, OpenQuestion } from '../components/OpenQuestionView';
import { InitResultView } from '../components/InitResultView';
import { InitStoryView } from '../components/InitStoryView';
import { CRTOverlay } from '../components/CRTOverlay';

type Phase = 'intro' | 'story' | 'questions' | 'result';

export const InitOpenPhase: React.FC = () => {
  const [phase, setPhase] = useState<Phase>('intro');
  const [story, setStory] = useState<{ lines: string[] } | null>(null);
  const [questions, setQuestions] = useState<OpenQuestion[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<string[]>([]);
  const [isLoadingQuestions, setIsLoadingQuestions] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string>('');
  const [result, setResult] = useState<{
    agentId: string;
    soulMd: string;
    core: Record<string, number>;
  } | null>(null);

  const handleStart = useCallback(async () => {
    setIsLoadingQuestions(true);
    setError('');
    try {
      const res = await fetch('/init-questions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        const text = await res.text();
        let msg = text;
        try {
          const json = JSON.parse(text);
          if (typeof json.detail === 'string') msg = json.detail;
        } catch {
          // ignore
        }
        throw new Error(msg);
      }
      const data = await res.json();
      setStory(data.story || { lines: [] });
      setQuestions(data.questions || []);
      setAnswers(new Array((data.questions || []).length || 7).fill(''));
      setCurrentIndex(0);
      setPhase('story');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setIsLoadingQuestions(false);
    }
  }, []);

  const handleAnswerChange = useCallback((value: string) => {
    setAnswers((prev) => {
      const next = [...prev];
      next[currentIndex] = value;
      return next;
    });
  }, [currentIndex]);

  const handleAnswerSubmit = useCallback(async () => {
    const value = answers[currentIndex]?.trim();
    if (!value) return;

    const isLast = currentIndex >= questions.length - 1;
    if (!isLast) {
      setCurrentIndex((i) => i + 1);
      return;
    }

    setIsCreating(true);
    setError('');
    try {
      const res = await fetch('/init-create-character', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answers }),
      });
      if (!res.ok) {
        const text = await res.text();
        let msg = text;
        try {
          const json = JSON.parse(text);
          if (typeof json.detail === 'string') msg = json.detail;
        } catch {
          // ignore
        }
        throw new Error(msg);
      }
      const data = await res.json();
      setResult({
        agentId: data.agent_id,
        soulMd: data.soul_md || '',
        core: data.core || {},
      });
      setPhase('result');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setIsCreating(false);
    }
  }, [answers, currentIndex, questions.length]);

  const handleStoryComplete = useCallback(() => {
    setPhase('questions');
  }, []);

  const handleReset = useCallback(() => {
    setPhase('intro');
    setStory(null);
    setQuestions([]);
    setCurrentIndex(0);
    setAnswers([]);
    setResult(null);
    setError('');
  }, []);

  const currentQuestion = questions[currentIndex];

  return (
    <div className="min-h-screen w-full bg-game-black">
      <CRTOverlay />

      <AnimatePresence mode="wait">
        {phase === 'intro' && (
          <motion.div
            key="intro"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, filter: 'blur(10px)', scale: 1.1 }}
            transition={{ duration: 1 }}
            className="flex flex-col items-center justify-center min-h-screen p-8 text-center relative z-10"
          >
            <div className="max-w-3xl w-full space-y-12">
              <div className="font-dialog text-2xl md:text-3xl text-game-lightGray leading-relaxed">
                Ти створиш персонажа для симуляції Island. Спочатку — історія. Потім — сім відкритих питань.
              </div>
              <div className="font-dialog text-3xl md:text-4xl text-white text-glow-cyan leading-relaxed">
                Відповідай вільно. Без варіантів. Твої слова формують профіль.
              </div>
              {error && (
                <div className="font-pixel text-game-red text-sm">{error}</div>
              )}
              <motion.button
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                whileHover={{
                  scale: 1.05,
                  boxShadow: '0 0 25px rgba(255,45,111,0.6)',
                }}
                whileTap={{ scale: 0.95 }}
                onClick={handleStart}
                disabled={isLoadingQuestions}
                className="mt-12 px-10 py-5 font-pixel text-xl text-game-pink border-2 border-game-pink box-glow-pink bg-game-black/50 backdrop-blur-sm uppercase tracking-widest transition-all duration-300 hover:bg-game-pink/10 disabled:opacity-50"
              >
                {isLoadingQuestions ? 'ЗАВАНТАЖЕННЯ...' : '[ ПОЧАТИ ]'}
              </motion.button>
            </div>
          </motion.div>
        )}

        {phase === 'story' && story && (
          <motion.div
            key="story"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0"
          >
            <InitStoryView
              lines={story.lines}
              onContinue={handleStoryComplete}
            />
          </motion.div>
        )}

        {phase === 'questions' && currentQuestion && (
          <motion.div
            key={`q-${currentIndex}`}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0"
          >
            <OpenQuestionView
              question={currentQuestion}
              totalQuestions={questions.length}
              value={answers[currentIndex] || ''}
              onChange={handleAnswerChange}
              onSubmit={handleAnswerSubmit}
              isLast={currentIndex >= questions.length - 1}
              isLoading={isCreating}
            />
            {error && (
              <div className="fixed bottom-8 left-1/2 -translate-x-1/2 font-pixel text-game-red text-sm bg-game-black/80 px-4 py-2 border border-game-red z-50">
                {error}
              </div>
            )}
          </motion.div>
        )}

        {phase === 'result' && result && (
          <motion.div
            key="result"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0"
          >
            <InitResultView
              agentId={result.agentId}
              soulMd={result.soulMd}
              core={result.core}
              onReset={handleReset}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

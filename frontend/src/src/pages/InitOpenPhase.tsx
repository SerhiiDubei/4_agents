import React, { useState, useCallback, useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { OpenQuestionView, OpenQuestion } from '../components/OpenQuestionView';
import { InitResultView } from '../components/InitResultView';
import { InitStoryView } from '../components/InitStoryView';
import { GamesResultsView } from '../components/GamesResultsView';
import { LeaderboardView } from '../components/LeaderboardView';
import { TimeWarsResultsView } from '../components/TimeWarsResultsView';
import { CRTOverlay } from '../components/CRTOverlay';

type Phase = 'intro' | 'story' | 'questions' | 'result' | 'games-results' | 'leaderboard' | 'time-wars';

function getInitialPhase(): Phase {
  if (typeof window === 'undefined') return 'intro';
  const view = new URLSearchParams(window.location.search).get('view');
  if (view === 'games-results') return 'games-results';
  if (view === 'leaderboard') return 'leaderboard';
  if (view === 'time-wars') return 'time-wars';
  return 'intro';
}

export const InitOpenPhase: React.FC = () => {
  const [phase, setPhase] = useState<Phase>(getInitialPhase);
  const [gamesCount, setGamesCount] = useState<number | null>(null);
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

  useEffect(() => {
    fetch('/api/games-count')
      .then((res) => (res.ok ? res.json() : { count: 0 }))
      .then((data: { count?: number }) => setGamesCount(typeof data.count === 'number' ? data.count : 0))
      .catch(() => setGamesCount(0));
  }, []);

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
            <div className="max-w-3xl w-full mx-auto space-y-12">
              <div className="font-dialog text-2xl md:text-3xl text-game-lightGray leading-relaxed">
                Ти створиш персонажа для симуляції Island. Спочатку — історія. Потім — сім відкритих питань.
              </div>
              <div className="font-dialog text-3xl md:text-4xl text-white text-glow-cyan leading-relaxed">
                Відповідай вільно. Без варіантів. Твої слова формують профіль.
              </div>
              {error && (
                <div className="font-pixel text-game-red text-sm">{error}</div>
              )}
              <div className="flex flex-col sm:flex-row flex-wrap gap-4 justify-center items-center mt-12 w-full">
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
                  className="px-10 py-5 font-pixel text-xl text-game-pink border-2 border-game-pink box-glow-pink bg-game-black/50 backdrop-blur-sm uppercase tracking-widest transition-all duration-300 hover:bg-game-pink/10 disabled:opacity-50"
                >
                  {isLoadingQuestions ? 'ЗАВАНТАЖЕННЯ...' : '[ ПОЧАТИ ]'}
                </motion.button>
                <motion.button
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.2 }}
                  whileHover={{
                    scale: 1.05,
                    boxShadow: '0 0 25px rgba(0,240,255,0.5)',
                  }}
                  whileTap={{ scale: 0.95 }}
                  onClick={() => setPhase('games-results')}
                  className="px-10 py-5 font-pixel text-lg text-game-cyan border-2 border-game-cyan box-glow-cyan bg-game-black/50 backdrop-blur-sm uppercase tracking-widest transition-all duration-300 hover:bg-game-cyan/10"
                >
                  РЕЗУЛЬТАТИ ({gamesCount !== null ? gamesCount : '…'} ігор)
                </motion.button>
                <motion.button
                  initial={{ opacity: 0, y: 20 }}
                  transition={{ delay: 0.25 }}
                  whileHover={{
                    scale: 1.05,
                    boxShadow: '0 0 25px rgba(234,179,8,0.5)',
                  }}
                  whileTap={{ scale: 0.95 }}
                  onClick={() => setPhase('leaderboard')}
                  className="px-10 py-5 font-pixel text-lg text-game-gold border-2 border-game-gold bg-game-black/50 backdrop-blur-sm uppercase tracking-widest transition-all duration-300 hover:bg-game-gold/10"
                >
                  [ ЛІДЕРБОРД ]
                </motion.button>
                <motion.button
                  initial={{ opacity: 0, y: 20 }}
                  transition={{ delay: 0.3 }}
                  whileHover={{
                    scale: 1.05,
                    boxShadow: '0 0 25px rgba(34,197,94,0.5)',
                  }}
                  whileTap={{ scale: 0.95 }}
                  onClick={() => window.open('/time_wars_board.html', '_blank')}
                  className="px-10 py-5 font-pixel text-lg text-emerald-400 border-2 border-emerald-400 bg-game-black/50 backdrop-blur-sm uppercase tracking-widest transition-all duration-300 hover:bg-emerald-400/10"
                >
                  [ ПОКАЗАТИ ГРУ ]
                </motion.button>
                <motion.button
                  initial={{ opacity: 0, y: 20 }}
                  transition={{ delay: 0.35 }}
                  whileHover={{
                    scale: 1.05,
                    boxShadow: '0 0 25px rgba(34,197,94,0.4)',
                  }}
                  whileTap={{ scale: 0.95 }}
                  onClick={() => setPhase('time-wars')}
                  className="px-10 py-5 font-pixel text-lg text-emerald-300 border-2 border-emerald-300/70 bg-game-black/50 backdrop-blur-sm uppercase tracking-widest transition-all duration-300 hover:bg-emerald-300/10"
                >
                  [ TIME WARS: РЕЗУЛЬТАТИ ]
                </motion.button>
              </div>
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

        {phase === 'games-results' && (
          <motion.div
            key="games-results"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0"
          >
            <GamesResultsView
              onBack={() => {
                setPhase('intro');
                fetch('/api/games-count')
                  .then((res) => (res.ok ? res.json() : { count: 0 }))
                  .then((data: { count?: number }) => setGamesCount(typeof data.count === 'number' ? data.count : 0))
                  .catch(() => setGamesCount(0));
              }}
            />
          </motion.div>
        )}

        {phase === 'leaderboard' && (
          <motion.div
            key="leaderboard"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0"
          >
            <LeaderboardView
              onBack={() => {
                setPhase('intro');
                fetch('/api/games-count')
                  .then((res) => (res.ok ? res.json() : { count: 0 }))
                  .then((data: { count?: number }) => setGamesCount(typeof data.count === 'number' ? data.count : 0))
                  .catch(() => setGamesCount(0));
              }}
            />
          </motion.div>
        )}

        {phase === 'time-wars' && (
          <motion.div
            key="time-wars"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0"
          >
            <TimeWarsResultsView onBack={() => setPhase('intro')} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { TypewriterText } from './TypewriterText';

export interface OpenQuestion {
  id: number;
  label: string;
  text: string;
}

interface OpenQuestionViewProps {
  question: OpenQuestion;
  totalQuestions: number;
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  isLast: boolean;
  isLoading?: boolean;
}

export const OpenQuestionView: React.FC<OpenQuestionViewProps> = ({
  question,
  totalQuestions,
  value,
  onChange,
  onSubmit,
  isLast,
  isLoading = false,
}) => {
  const [showInput, setShowInput] = useState(false);

  const handleSubmit = () => {
    if (value.trim()) {
      onSubmit();
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-4 md:p-8 relative z-10">
      {/* Progress */}
      <div className="absolute top-8 left-8 font-pixel text-sm text-game-cyan text-glow-cyan">
        {question.id} / {totalQuestions}
      </div>

      <motion.div
        key={question.id}
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 1.05, filter: 'blur(10px)', y: -20 }}
        transition={{ duration: 0.6, ease: 'easeOut' }}
        className="w-full max-w-4xl bg-game-darkPurple/80 backdrop-blur-md border border-game-cyan box-glow-cyan p-6 md:p-10 rounded-sm relative overflow-hidden"
      >
        <div className="absolute inset-0 bg-scanlines opacity-20 pointer-events-none" />

        <div className="mb-2">
          <span className="font-pixel text-xs text-game-cyan/80 uppercase tracking-wider">
            {question.label}
          </span>
        </div>

        <div className="min-h-[100px] mb-8 relative z-10">
          <TypewriterText
            key={`q-${question.id}`}
            text={question.text}
            className="font-dialog text-2xl md:text-3xl text-white leading-relaxed"
            speed={20}
            onComplete={() => setShowInput(true)}
          />
        </div>

        {showInput && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="relative z-10 space-y-4"
          >
            <textarea
              value={value}
              onChange={(e) => onChange(e.target.value)}
              placeholder="Твоя відповідь..."
              rows={4}
              autoFocus
              disabled={isLoading}
              className="w-full bg-game-black/50 border border-game-cyan/50 text-white font-dialog text-lg p-4 resize-none placeholder-game-lightGray/40 focus:outline-none focus:border-game-cyan focus:ring-1 focus:ring-game-cyan disabled:opacity-50"
            />
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={handleSubmit}
              disabled={!value.trim() || isLoading}
              className="w-full py-4 border-2 border-game-cyan text-game-cyan font-pixel text-sm uppercase tracking-widest hover:bg-game-cyan/20 hover:text-glow-cyan disabled:opacity-30 disabled:cursor-not-allowed transition-all duration-200"
            >
              {isLoading ? '...' : isLast ? 'СТВОРИТИ ПЕРСОНАЖА' : 'ДАЛІ'}
            </motion.button>
          </motion.div>
        )}
      </motion.div>
    </div>
  );
};

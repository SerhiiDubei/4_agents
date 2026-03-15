import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { TypewriterText } from './TypewriterText';

interface InitStoryViewProps {
  lines: string[];
  onContinue: () => void;
}

export const InitStoryView: React.FC<InitStoryViewProps> = ({
  lines,
  onContinue,
}) => {
  const [currentLine, setCurrentLine] = useState(0);
  const [showContinue, setShowContinue] = useState(false);

  useEffect(() => {
    setCurrentLine(0);
    setShowContinue(false);
  }, []);

  const handleLineComplete = () => {
    if (currentLine < lines.length - 1) {
      setTimeout(() => {
        setCurrentLine((prev) => prev + 1);
      }, 600);
    } else {
      setTimeout(() => {
        setShowContinue(true);
      }, 500);
    }
  };

  const displayLines = lines.length > 0 ? lines : [
    'Завантаження історії...',
  ];

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-8 text-center relative z-10 bg-game-black">
      <div className="max-w-3xl w-full space-y-8">
        <div className="min-h-[280px] flex flex-col justify-center space-y-6">
          <AnimatePresence>
            {displayLines.map(
              (line, index) =>
                index <= currentLine && (
                  <motion.div
                    key={`story-${index}`}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="min-h-[36px]"
                  >
                    <TypewriterText
                      text={line}
                      className={`font-dialog text-xl md:text-2xl leading-relaxed ${
                        index === displayLines.length - 1 && line.trim()
                          ? 'text-white text-glow-cyan'
                          : 'text-game-lightGray'
                      }`}
                      speed={25}
                      onComplete={
                        index === currentLine ? handleLineComplete : undefined
                      }
                    />
                  </motion.div>
                ),
            )}
          </AnimatePresence>
        </div>

        <AnimatePresence>
          {showContinue && (
            <motion.button
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              whileHover={{
                scale: 1.05,
                boxShadow: '0 0 25px rgba(0,240,255,0.5)',
              }}
              whileTap={{ scale: 0.95 }}
              onClick={onContinue}
              className="mt-12 px-10 py-4 font-pixel text-lg text-game-cyan border-2 border-game-cyan box-glow-cyan bg-game-black/50 backdrop-blur-sm uppercase tracking-widest transition-all duration-300 hover:bg-game-cyan/10"
            >
              [ ДАЛІ — ДО ПИТАНЬ ]
            </motion.button>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};

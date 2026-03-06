import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { StoryBeat } from '../types/game';
import { TypewriterText } from './TypewriterText';

interface StoryBeatViewProps {
  beat: StoryBeat;
  onContinue: () => void;
}

export const StoryBeatView: React.FC<StoryBeatViewProps> = ({ beat, onContinue }) => {
  const [currentLine, setCurrentLine] = useState(0);
  const [showContinue, setShowContinue] = useState(false);

  useEffect(() => {
    setCurrentLine(0);
    setShowContinue(false);
  }, [beat.id]);

  const handleLineComplete = () => {
    if (currentLine < beat.lines.length - 1) {
      setTimeout(() => setCurrentLine((prev) => prev + 1), 800);
    } else {
      setTimeout(() => setShowContinue(true), 500);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-4 md:p-8 relative z-10">
      <motion.div
        key={beat.id}
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-4xl space-y-6"
      >
        <AnimatePresence mode="wait">
          {beat.lines.map(
            (line, index) =>
              index <= currentLine && (
                <motion.div
                  key={`${beat.id}-${index}`}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="bg-game-darkPurple/80 backdrop-blur-md border border-game-cyan/50 p-6 rounded-sm"
                >
                  {index < currentLine ? (
                    <p className="font-dialog text-2xl md:text-3xl text-game-lightGray leading-relaxed">
                      {line}
                    </p>
                  ) : (
                    <TypewriterText
                      text={line}
                      speed={25}
                      className="font-dialog text-2xl md:text-3xl text-game-lightGray leading-relaxed"
                      onComplete={handleLineComplete}
                    />
                  )}
                </motion.div>
              )
          )}
        </AnimatePresence>

        {showContinue && (
          <motion.button
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={onContinue}
            className="mt-8 px-8 py-4 border border-game-cyan text-game-cyan font-pixel text-lg hover:bg-game-cyan/20 transition-colors"
          >
            ДАЛІ
          </motion.button>
        )}
      </motion.div>
    </div>
  );
};

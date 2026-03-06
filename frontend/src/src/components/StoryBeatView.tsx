import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { StoryBeat } from '../types/game';
import { TypewriterText } from './TypewriterText';

interface StoryBeatViewProps {
  beat: StoryBeat;
  onContinue: () => void;
}

export const StoryBeatView: React.FC<StoryBeatViewProps> = ({
  beat,
  onContinue,
}) => {
  const [currentLine, setCurrentLine] = useState(0);
  const [showContinue, setShowContinue] = useState(false);

  useEffect(() => {
    setCurrentLine(0);
    setShowContinue(false);
  }, [beat.id]);

  const handleLineComplete = () => {
    if (currentLine < beat.lines.length - 1) {
      setTimeout(() => {
        setCurrentLine((prev) => prev + 1);
      }, 800);
    } else {
      setTimeout(() => {
        setShowContinue(true);
      }, 500);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-8 text-center relative z-10">
      <div className="max-w-3xl w-full space-y-12">
        <div className="min-h-[200px] flex flex-col justify-center space-y-8">
          <AnimatePresence>
            {beat.lines.map(
              (line, index) =>
                index <= currentLine && (
                  <motion.div
                    key={`${beat.id}-${index}`}
                    initial={{
                      opacity: 0,
                      y: 10,
                    }}
                    animate={{
                      opacity: 1,
                      y: 0,
                    }}
                    className="min-h-[40px]"
                  >
                    <TypewriterText
                      text={line}
                      className={`font-dialog text-2xl md:text-3xl leading-relaxed ${
                        index === beat.lines.length - 1
                          ? 'text-white text-glow-cyan'
                          : 'text-game-lightGray'
                      }`}
                      speed={30}
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
              initial={{
                opacity: 0,
                y: 20,
              }}
              animate={{
                opacity: 1,
                y: 0,
              }}
              exit={{
                opacity: 0,
              }}
              whileHover={{
                scale: 1.05,
                textShadow: '0 0 15px rgb(0,240,255)',
                boxShadow:
                  '0 0 25px rgba(0,240,255,0.4), inset 0 0 15px rgba(0,240,255,0.2)',
              }}
              whileTap={{
                scale: 0.95,
              }}
              onClick={onContinue}
              className="mt-12 px-10 py-4 font-pixel text-lg text-game-cyan border-2 border-game-cyan box-glow-cyan bg-game-black/50 backdrop-blur-sm uppercase tracking-widest transition-all duration-300 hover:bg-game-cyan/10"
            >
              [ ДАЛІ ]
            </motion.button>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};
